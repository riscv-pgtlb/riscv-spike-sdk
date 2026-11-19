#!/usr/bin/env python3
"""Combine existing static, artifact and runtime checks with per-case evidence."""
import argparse
import codecs
from datetime import datetime, timezone
import getpass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
GUARDS = ("DBCN READ", "PMU", "DBTR", "SSE", "MPXY", "HSM STATUS", "SUSP", "FWFT", "CPPC")
RUNTIME_CASES = (
    ("seal", "PMP.Virt 策略封存与内核确认"),
    ("hs_ram", "HS RAM 执行权限：封存前允许，封存后拒绝"),
    ("hs_text", "内核 text 写保护：可写别名访问被拒绝"),
    ("hs_rodata", "内核 rodata 写保护：可写别名访问被拒绝"),
    ("sbi_before", "封存前 SBI 接口限制检查（9/9）"),
    ("sbi_after", "封存后 SBI 接口限制检查（9/9）"),
    ("host_before", "guest 启动前：host 检查与 HU–HS–HU 同页探针"),
    ("vs_hs", "VS–HS–VS 同物理页执行权限对照"),
    ("guest", "guest 内核、内存与时钟推进"),
    ("guest_shutdown", "guest 自动关机请求"),
    ("guest_return", "guest 正常退出并返回 host"),
    ("host_after", "guest 返回后：host 检查与 HU–HS–HU 同页复测"),
    ("runtime", "完整回归结果与事件顺序"),
)
HOST_PASS = "VIRT-KVM HOST CHECK PASS: seal, HS 6/6, SBI guard 18/18, U/HS/U, /dev/kvm"
USER_PASS = "PMP.Virt USER SUMMARY: PASS U-success / HS-access-fault / U-success"


def colored(text, status):
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb":
        code = {"PASS": "32", "FAIL": "31", "SKIP": "33", "RUN": "36"}[status]
        return f"\033[1;{code}m{text}\033[0m"
    return text


def report(status, message, number=None):
    prefix = (f"[TEST {number:02d}]" if number is not None else "").ljust(9) + " "
    print(f"{prefix}{colored(f'[{status:4}]', status)} {message}", flush=True)


def terminal_text(text):
    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", text)
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text.replace("\r", ""))


def canonical_lines(text):
    text = terminal_text(text)
    return [re.sub(r"^\[\s*\d+(?:\.\d+)?\]\s*", "", line).rstrip()
            for line in text.splitlines()]


def ordered(lines, patterns):
    position = 0
    for pattern in patterns:
        for index in range(position, len(lines)):
            if re.fullmatch(pattern, lines[index]):
                position = index + 1
                break
        else:
            return False
    return True


def same_page(lines):
    return ordered(lines, (
        r"PASS U execute before HS probe: value=42 VA=0x[0-9a-fA-F]+",
        r"PASS HS denied same physical page: PA=0x[0-9a-fA-F]+ cause=1",
        r"PASS U execute after HS probe: value=42", re.escape(USER_PASS), re.escape(HOST_PASS)))


def vs_hs_same_page(lines):
    checker = ROOT / "tests/pmp-virt/runtime/check-virt-vs-hs.sh"
    result = subprocess.run(["sh", str(checker)], input="\n".join(lines) + "\n",
                            text=True, capture_output=True)
    return result.returncode == 0


def runtime_results(text, expected_versions=None):
    """Only real complete output lines count; shell echoes are not results."""
    lines = canonical_lines(text)
    outcomes = {key: False for key, _ in RUNTIME_CASES}
    outcomes["seal"] = ordered(lines, (r"PMP\.Virt SEALED: text=.*", r"PMP\.Virt seal acknowledged"))
    for key, name, cause in (("hs_ram", "HS RAM execute", 1),
                             ("hs_text", "text writable alias", 7),
                             ("hs_rodata", "rodata writable alias", 7)):
        outcomes[key] = ordered(lines, (
            rf"PMP\.Virt TEST PASS before {name} cause=0(?: .*)?",
            rf"PMP\.Virt TEST PASS after {name} cause={cause}(?: .*)?"))
    for key, phase in (("sbi_before", "before seal"), ("sbi_after", "after seal")):
        prefix = f"PMP.Virt SBI GUARD PASS {phase} "
        actual = [line for line in lines if line.startswith(prefix)]
        expected = {prefix + f"{name} probe=0 error=-2 buffer=unchanged" for name in GUARDS}
        outcomes[key] = len(actual) == 9 and set(actual) == expected

    def index(marker):
        return lines.index(marker) if marker in lines else None

    before = index("VIRT-REGRESSION HOST BEFORE PASS")
    returned = index("VIRT-REGRESSION GUEST RETURNED")
    after = index("VIRT-REGRESSION HOST AFTER PASS")
    if before is not None:
        outcomes["host_before"] = same_page(lines[:before])
    if before is not None and returned is not None and before < returned:
        guest = lines[before + 1:returned]
        outcomes["vs_hs"] = vs_hs_same_page(guest)
        check = r"(?:check-virt-guest\[\d+\]: )?VIRT-REGRESSION GUEST PASS"
        shutdown = r"(?:echo\[\d+\]: )?VIRT-REGRESSION GUEST SHUTDOWN"
        outcomes["guest"] = ordered(guest, (check,))
        outcomes["guest_shutdown"] = ordered(guest, (check, shutdown))
        outcomes["guest_return"] = outcomes["guest_shutdown"]
    if returned is not None and after is not None and returned < after:
        outcomes["host_after"] = same_page(lines[returned + 1:after])
    if expected_versions:
        host_marker = f"VIRT TOOLS VERSION PASS role=host version={expected_versions['host']}"
        outcomes["host_before"] &= before is not None and host_marker in lines[:before]
        outcomes["host_after"] &= returned is not None and after is not None and host_marker in lines[returned + 1:after]
        guest_pattern = (r"(?:check-virt-tools\[\d+\]: )?VIRT TOOLS VERSION PASS role=guest version="
                         + re.escape(expected_versions["guest"]))
        guest_version_ok = (before is not None and returned is not None
                            and ordered(lines[before + 1:returned], (guest_pattern,)))
        outcomes["guest"] &= guest_version_ok
    outcomes["runtime"] = ordered(lines, tuple(re.escape(marker) for marker in (
        "VIRT-REGRESSION HOST BEFORE PASS", "VIRT-REGRESSION GUEST RETURNED",
        "VIRT-REGRESSION HOST AFTER PASS", "VIRT-REGRESSION ALL PASS")))
    if re.search(r"PMP\.Virt .*FAIL|PMP\.Virt seal FATAL|VIRT-REGRESSION FAIL|Kernel panic", text):
        outcomes["runtime"] = False
        outcomes["vs_hs"] = False
    return outcomes


class Redactor:
    """Keep enough trailing text to redact a password split over reads."""
    def __init__(self, secret):
        self.secret = secret
        self.pending = ""

    def feed(self, text, final=False):
        self.pending += text
        if not self.secret:
            output, self.pending = self.pending, ""
            return output
        cut = len(self.pending) if final else max(0, len(self.pending) - len(self.secret) + 1)
        start = self.pending.find(self.secret)
        while start >= 0:
            if start < cut < start + len(self.secret):
                cut = start
                break
            start = self.pending.find(self.secret, start + 1)
        output = self.pending[:cut].replace(self.secret, "[REDACTED]")
        self.pending = self.pending[cut:]
        return output


def read_password(filename):
    if filename:
        with Path(filename).open() as stream:
            mode = os.fstat(stream.fileno()).st_mode
            if not stat.S_ISREG(mode) or mode & 0o077:
                raise RuntimeError("Password file must be a regular file readable only by its owner (chmod 600)")
            password = stream.read().removesuffix("\n")
    else:
        if not sys.stdin.isatty():
            raise RuntimeError("Debian login needs a terminal or PMPVIRT_PASSWORD_FILE pointing to a chmod-600 file")
        password = getpass.getpass("外层 Debian root 密码（不保存）：")
    if not password or any(char in password for char in "\r\n\x00"):
        raise RuntimeError("Password must be a nonempty single line")
    return password


def failure_info(error, transcript="", cases=()):
    """Explain observed failures without assuming every failure is protection-related."""
    reason = error or "部分测试点没有完整成功证据"
    info = {"code": "INCOMPLETE_RESULTS", "stage": "结果核对", "reason": reason,
            "actions": ["查看 console.log 中第一个错误及其前后输出。",
                        "对照 result.json 中 FAIL/SKIP 的测试点；缺少证据不能算通过。"],
            "blocked": "本轮未取得此项完整成功证据"}
    if "authentication failed" in reason:
        info.update(code="AUTH_REJECTED", stage="外层 Debian 登录",
                    reason="Debian 拒绝了 root 登录，完整回归命令尚未执行；不能据此判断 PMP.Virt 保护失败。",
                    actions=["用同一组磁盘参数执行 make run-virt-dual-debian，手动验证 root 登录。",
                             "确认输入的是当前外层磁盘的 root 密码；重建后的密码可能与旧盘不同。",
                             "手动登录仍失败时检查账号状态或登录策略；不要通过重建磁盘盲目排错。"],
                    blocked="外层登录被拒绝，未启动此项")
    elif reason == "Interrupted":
        info.update(code="INTERRUPTED", stage="运行被中断",
                    reason="本次执行被中断，尚未完成的测试没有结果，不代表保护检查失败。",
                    actions=["重新执行 make pmpvirt-test；等待进度提示或指定的超时时间。",
                             "若再次停滞，根据 console.log 最后一条输出定位阶段。"],
                    blocked="运行被中断，此项没有完整结果")
    elif "timed out" in reason or "timeout" in reason.lower():
        info.update(code="TIMEOUT", stage="运行超时",
                    actions=["查看 console.log 末尾，区分仍在启动、等待登录或 guest 未退出。",
                             "确认不是命令缺失或登录失败后，再按需要提高 PMPVIRT_TIMEOUT。"],
                    blocked="运行超时，此项没有完整结果")
    elif re.search(r"VIRT TOOLS .*FAIL|VIRT TOOLS VERSION MISMATCH|check-virt-tools:.*(?:not found|No such file)", transcript):
        info.update(code="TOOLS_MISMATCH", stage="已安装工具版本检查",
                    reason="磁盘内工具缺失、内容变化或与服务器当前工具版本不一致；旧环境也可能尚未安装校验命令。",
                    actions=["查看 console.log 中具体的文件路径或 expected/installed 版本。",
                             "关闭两层后，使用同一组磁盘参数执行 make debian-update，再重新测试。"],
                    blocked="工具版本检查未通过，未完成此项")
    elif re.search(r"(?m)^[^\r\n]*test-virt-debian-all[^\r\n]*: (?:not found|No such file or directory|cannot open[^\r\n]*No such file)[^\r\n]*$", terminal_text(transcript)) and not re.search(r"Kernel panic|Oops|PMP\.Virt .*FAIL", transcript):
        info.update(code="HOST_SUITE_MISSING", stage="调用外层完整套件",
                    reason="外层无法找到或打开 test-virt-debian-all；可能尚未安装完整工具包。",
                    actions=["关闭两层后，用相同磁盘参数运行 make debian-update。",
                             "重新启动确认 /usr/local/bin/test-virt-debian-all 存在，再执行统一测试。"],
                    blocked="外层完整套件不可用，未完成此项")
    elif "Protection failure" in reason or re.search(r"PMP\.Virt .*FAIL|PMP\.Virt seal FATAL|Kernel panic|Oops", transcript):
        info.update(code="RUNTIME_FAILURE", stage="保护探针或内核运行",
                    reason="控制台出现保护失败或内核 panic，需要核对具体探针；不是普通登录失败。",
                    actions=["查看 console.log 中首个 FAIL/FATAL/panic 的原因、地址和异常码。",
                             "核对本轮 manifest.json 与源码版本；不要只截取最后一行汇总。"],
                    blocked="保护探针或内核运行失败，未取得此项完整结果")
    elif "Disk check failed" in reason or "disk" in reason.lower() and "separate" in reason:
        info.update(code="DISK_PREFLIGHT", stage="磁盘检查",
                    actions=["确认两块磁盘存在、相互独立且可读写。",
                             "先正常关闭占用这两块磁盘的虚拟机，再重试。"],
                    blocked="磁盘检查未通过，未启动此项")
    else:
        failed = next((case for case in cases if case["status"] == "FAIL"), None)
        if failed and failed["id"] in ("static", "artifacts"):
            name = "static.log" if failed["id"] == "static" else "verify.log"
            info.update(code="STATIC_FAILURE" if name == "static.log" else "ARTIFACT_FAILURE",
                        stage=failed["name"], reason=f"前置检查失败，详情见 {name}；虚拟机回归尚未开始。",
                        actions=[f"先解决 {name} 中的第一个错误，再重新运行。"],
                        blocked="前置检查失败，未启动此项")
    return info


def stop_process(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def run_buildroot(command, env, log_path, timeout):
    with log_path.open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            result = process.wait(timeout=timeout)
            return None if result == 0 else "Buildroot runtime failed; see console.log"
        except subprocess.TimeoutExpired:
            return "Buildroot runner exceeded its timeout"
        finally:
            stop_process(process)


def run_debian(command, env, password, log_path, timeout, expected_versions=None):
    token = uuid.uuid4().hex
    done = f"PMPVIRT-SUITE-EXIT-{token}"
    version_args = ""
    prefix = ""
    if expected_versions:
        for role in ("host", "guest"):
            if not re.fullmatch(r"[0-9a-f]{64}", expected_versions[role]):
                raise RuntimeError("Invalid server expected tools version")
        version_args = f" {expected_versions['host']} {expected_versions['guest']}"
        prefix = ("/usr/local/bin/check-virt-tools --role host --expect-version "
                  + expected_versions["host"] + " && ")
    setup = (prefix + "/usr/local/bin/test-virt-debian-all /dev/vdb" + version_args + "; suite_rc=$?; "
             f"printf '\\n{done} %s\\n' \"$suite_rc\"; systemctl poweroff\n")
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                               start_new_session=True)
    chunks = queue.Queue()

    def pump():
        try:
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                chunks.put(chunk)
        finally:
            chunks.put(None)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    redactor = Redactor(password)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    transcript = ""
    state = "login"
    deadline = time.monotonic() + timeout
    next_progress = time.monotonic() + 30
    error = None

    def send(text):
        process.stdin.write(text.encode())
        process.stdin.flush()

    with log_path.open("w") as log:
        try:
            while time.monotonic() < deadline:
                if time.monotonic() >= next_progress:
                    description = {"login": "等待外层登录提示", "password": "等待密码提示",
                                   "shell": "等待外层命令提示符", "running": "完整回归运行中"}[state]
                    report("RUN", f"{description}；详细输出：{log_path}")
                    next_progress = time.monotonic() + 30
                try:
                    data = chunks.get(timeout=0.5)
                except queue.Empty:
                    continue
                if data is None:
                    break
                text = decoder.decode(data)
                log.write(redactor.feed(text))
                log.flush()
                transcript += text
                tail = terminal_text(transcript[-8192:])
                if state == "login" and re.search(r"(?:^|\n)[^\n]*login:\s*$", tail):
                    send("root\n")
                    state = "password"
                    report("RUN", "已识别外层登录提示，提交 root 用户名")
                elif state == "password" and re.search(r"(?:^|\n)Password:\s*$", tail):
                    send(password + "\n")
                    state = "shell"
                    report("RUN", "已提交登录密码，等待外层命令提示符")
                elif state in ("password", "shell") and re.search(r"(?:^|\n)root@[^\n]*#\s*$", tail):
                    send(setup)
                    state = "running"
                    report("RUN", "外层已登录，执行现有双 Debian 完整套件")
                elif state == "shell" and re.search(r"Login incorrect|Authentication failure", tail):
                    raise RuntimeError("Debian root authentication failed")
                if re.search(r"PMP\.Virt .*FAIL|PMP\.Virt seal FATAL|Kernel panic", transcript):
                    raise RuntimeError("Protection failure or kernel panic; see console.log")
            else:
                raise RuntimeError(f"Debian runtime timed out after {timeout} seconds (state={state})")
            process.wait(timeout=15)
            exits = re.findall(rf"(?m)^{re.escape(done)} (\d+)\r*$", transcript)
            if process.returncode != 0 or exits != ["0"]:
                raise RuntimeError("Runtime did not finish with a successful suite exit and clean QEMU shutdown")
        except (Exception, KeyboardInterrupt) as caught:
            error = str(caught) or "Interrupted"
        finally:
            stop_process(process)
            reader.join(timeout=2)
            # Preserve any final output queued before termination.
            while not chunks.empty():
                data = chunks.get_nowait()
                if data:
                    text = decoder.decode(data)
                    transcript += text
                    log.write(redactor.feed(text))
            remainder = decoder.decode(b"", final=True)
            transcript += remainder
            log.write(redactor.feed(remainder))
            log.write(redactor.feed("", final=True))
            process.stdin.close()
            process.stdout.close()
    return transcript, error


class Suite:
    def __init__(self, folder, system):
        self.folder = folder
        self.system = system
        self.started = time.monotonic()
        self.cases = [{"id": key, "name": name, "status": "SKIP", "detail": "未执行"}
                      for key, name in (("static", "SDK 单元测试"), ("artifacts", "构建产物完整性与内核—固件配对"),
                                        ("environment", "运行环境与磁盘可用性"), *RUNTIME_CASES,
                                        ("shutdown", "测试命令与 QEMU 正常退出"))]
        for number, case in enumerate(self.cases, start=1):
            case["number"] = number
        self.error = None
        self.transcript = ""
        self.expected_tools = None
        self.reported = set()

    def report_case(self, case, status, message):
        number = None if status == "RUN" else case["number"]
        report(status, message, number)

    def mark(self, key, status, detail=""):
        case = next(item for item in self.cases if item["id"] == key)
        case.update(status=status, detail=detail)
        self.reported.add(key)
        self.report_case(case, status, case['name'] + (f"：{detail}" if detail and status != "PASS" else ""))

    def command(self, key, command, logfile, timeout=120, env=None):
        case = next(item for item in self.cases if item['id'] == key)
        self.report_case(case, "RUN", case["name"])
        with (self.folder / logfile).open("w") as log:
            try:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=timeout)
                if result.returncode:
                    raise RuntimeError(f"Command exited {result.returncode}; see {logfile}")
            except (OSError, subprocess.SubprocessError, RuntimeError):
                self.mark(key, "FAIL", f"查看 {logfile}")
                raise
        self.mark(key, "PASS", logfile)

    def finish(self):
        passed = self.error is None and all(item["status"] == "PASS" for item in self.cases)
        diagnostics = None if passed else failure_info(self.error, self.transcript, self.cases)
        if diagnostics:
            for case in self.cases:
                if case["status"] == "SKIP" and case["detail"] == "未执行":
                    case["detail"] = diagnostics["blocked"]
        state = {"status": "PASS" if passed else "FAIL", "system": self.system,
                 "error": self.error, "diagnostics": diagnostics, "cases": self.cases,
                 "expected_tools": self.expected_tools,
                 "elapsed_seconds": round(time.monotonic() - self.started, 2)}
        counts = {status: sum(case["status"] == status for case in self.cases)
                  for status in ("PASS", "FAIL", "SKIP")}
        state["counts"] = {"total": len(self.cases), "passed": counts["PASS"],
                           "failed": counts["FAIL"], "skipped": counts["SKIP"]}
        (self.folder / "result.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        footer = [f"结果：{state['status']}（{counts['PASS']}/{len(self.cases)}）",
                  f"耗时：{state['elapsed_seconds']:.2f} 秒",
                  f"证据目录：{self.folder}"]
        lines = []
        lines.extend("{} [{}] {} {}".format(f"[TEST {case['number']:02d}]".ljust(9),
                                          case["status"], case["name"], case["detail"] if case["status"] != "PASS" else "").rstrip()
                     for case in self.cases)
        if self.error:
            lines.append("Error: " + self.error)
        if diagnostics:
            lines += ["", "失败阶段：" + diagnostics["stage"], "原因：" + diagnostics["reason"]]
            lines += [f"建议 {index}：{action}" for index, action in enumerate(diagnostics["actions"], 1)]
        lines += ["", *footer]
        (self.folder / "summary.txt").write_text("\n".join(lines) + "\n")
        files = sorted(p for p in self.folder.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
        (self.folder / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(self.folder)}\n" for path in files))
        if diagnostics:
            print(f"          失败阶段：{diagnostics['stage']} [{diagnostics['code']}]", flush=True)
            print(f"          原因：{diagnostics['reason']}", flush=True)
            for index, action in enumerate(diagnostics["actions"], 1):
                print(f"          建议 {index}：{action}", flush=True)
            print(f"          运行日志：{self.folder / 'console.log'}" if (self.folder / "console.log").exists()
                  else f"          检查日志：{self.folder}", flush=True)
            print(f"          本轮输入：{self.folder / 'inputs.json'}", flush=True)
        for case in self.cases:
            if case["status"] == "SKIP" and case["id"] not in self.reported:
                self.report_case(case, "SKIP", f"{case['name']}：{case['detail']}")
        print("\n" + "\n".join(footer), flush=True)
        return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=("debian", "buildroot"), default="debian")
    parser.add_argument("--host-disk", type=Path, default=ROOT / "images/debian/debian-host.raw")
    parser.add_argument("--guest-disk", type=Path, default=ROOT / "images/debian/debian-guest.raw")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("timeout must be positive")
    folder = ROOT / "build/virt-kvm/logs" / ("suite-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    folder.mkdir(parents=True)
    folder.chmod(0o700)
    suite = Suite(folder, args.system)
    transcript = ""
    runtime_started = False
    phase = "environment"
    try:
        info = {"started_utc": datetime.now(timezone.utc).isoformat(), "timeout": args.timeout,
                "host_disk": str(args.host_disk.resolve()), "guest_disk": str(args.guest_disk.resolve())}
        for name, command in (("sdk_commit", ["git", "rev-parse", "HEAD"]),
                              ("sdk_status", ["git", "status", "--porcelain"])):
            info[name] = subprocess.check_output(command, cwd=ROOT, text=True)
        (folder / "inputs.json").write_text(json.dumps(info, indent=2) + "\n")
        phase = "static"
        suite.command("static", [sys.executable, "-B", "-m", "unittest", "discover", "-s",
                                 "tests/pmp-virt/unit", "-p", "test_*.py", "-v"], "static.log")
        phase = "artifacts"
        suite.command("artifacts", [sys.executable, "-B", "scripts/build/virt-kvm.py", "verify"], "verify.log")
        shutil.copyfile(ROOT / "build/virt-kvm/manifest.json", folder / "manifest.json")
        shutil.copyfile(ROOT / "conf/pmp-virt/sources.json", folder / "sources.json")
        phase = "environment"
        env = dict(os.environ)
        for name in ("VIRT_HOST_DISK", "VIRT_DEBIAN_DISK"):
            env.pop(name, None)
        if args.system == "debian":
            versions_spec = importlib.util.spec_from_file_location("suite_tool_manifest", ROOT / "scripts/debian/install/tool-manifest.py")
            versions_module = importlib.util.module_from_spec(versions_spec)
            versions_spec.loader.exec_module(versions_module)
            suite.expected_tools = versions_module.expected_versions(ROOT)
            (folder / "expected-tools.json").write_text(json.dumps(suite.expected_tools, indent=2) + "\n")
            spec = importlib.util.spec_from_file_location("suite_maintenance", ROOT / "scripts/debian/common/maintenance.py")
            maintenance = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(maintenance)
            host, guest = args.host_disk.resolve(), args.guest_disk.resolve()
            if not host.is_file() or not guest.is_file() or host.samefile(guest):
                raise RuntimeError("Debian needs two existing, separate disks; prepare them first")
            maintenance.check_stopped(host, guest)
            password = read_password(os.environ.get("PMPVIRT_PASSWORD_FILE"))
            env.update(DEBIAN_HOST_DISK=str(host), DEBIAN_GUEST_DISK=str(guest))
            suite.mark("environment", "PASS", "磁盘已检查；使用外层 root 登录")
            runtime_started = True
            transcript, error = run_debian(["bash", str(ROOT / "scripts/debian/run/run-dual-debian.sh")],
                                            env, password, folder / "console.log", args.timeout,
                                            expected_versions=suite.expected_tools)
            del password
        else:
            suite.mark("environment", "PASS", "复用现有 Buildroot 自动回归入口")
            runtime_started = True
            command = [sys.executable, "-B", str(ROOT / "tests/pmp-virt/regression/buildroot/run-regression.py"),
                       "--timeout", str(args.timeout)]
            error = run_buildroot(command, env, folder / "console.log", args.timeout + 45)
            transcript = (folder / "console.log").read_text()
        outcomes = runtime_results(transcript, expected_versions=suite.expected_tools)
        suite.transcript = transcript
        diagnostics = failure_info(error, transcript) if error else None
        for key in outcomes:
            suite.mark(key, "PASS" if outcomes[key] else ("FAIL" if error is None else "SKIP"),
                       "" if outcomes[key] else (diagnostics["blocked"] if diagnostics else "缺少成功证据，查看 console.log"))
        suite.mark("shutdown", "PASS" if error is None else "FAIL", error or "")
        if error or not all(outcomes.values()):
            raise RuntimeError(error or "Runtime output is missing required individual test results")
    except (Exception, KeyboardInterrupt) as caught:
        suite.error = str(caught) or "Interrupted"
        key = "shutdown" if runtime_started else phase
        case = next(item for item in suite.cases if item["id"] == key)
        if case["status"] == "SKIP":
            suite.mark(key, "FAIL", suite.error)
    return 0 if suite.finish() else 1


if __name__ == "__main__":
    sys.exit(main())
