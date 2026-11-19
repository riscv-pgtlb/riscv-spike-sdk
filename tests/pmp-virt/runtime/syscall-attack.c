#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

/* The kernel chooses every target and value; this request is output only. */
struct pv_access_result { uint64_t cause, before, after; };
struct pv_syscall_request {
    uint64_t version, count;
    struct pv_access_result results[4];
};
#define PV_SYSCALL_PROBE _IOR('V', 0x58, struct pv_syscall_request)
_Static_assert(sizeof(struct pv_syscall_request) == 112, "probe ABI size");

static void die(const char *what)
{
    perror(what);
    exit(1);
}

static void reject(int fd, void *output, int expected, const char *name)
{
    errno = 0;
    long rc = syscall(SYS_ioctl, fd, PV_SYSCALL_PROBE, output);
    if (rc != -1 || errno != expected) {
        fprintf(stderr, "SYSCALL-ATTACK FAIL %s rc=%ld errno=%d expected=%d\n",
                name, rc, errno, expected);
        exit(1);
    }
}

int main(void)
{
    static const char *names[] = {
        "ordinary-data-store-control", "HS-data-page-execute",
        "kernel-text-store", "kernel-rodata-store"
    };
    static const uint64_t causes[] = {0, 1, 7, 7};
    const unsigned rounds = 3;
    struct pv_syscall_request output;
    unsigned passed = 0;
    int status;

    setvbuf(stdout, NULL, _IONBF, 0);
    if (sysconf(_SC_PAGESIZE) != 4096 || geteuid() != 0) {
        fputs("SYSCALL-ATTACK FAIL requires root and 4 KiB pages\n", stderr);
        return 1;
    }
    int fd = open("/dev/pvtest", O_RDWR | O_CLOEXEC);
    if (fd < 0)
        die("open /dev/pvtest");
    reject(fd, NULL, EFAULT, "null-output");
    pid_t child = fork();
    if (child < 0)
        die("fork");
    if (!child) {
        if (setgid(65534) || setuid(65534))
            die("drop identity");
        reject(fd, &output, EPERM, "unprivileged-inherited-fd");
        _exit(0);
    }
    if (waitpid(child, &status, 0) != child)
        die("waitpid");
    if (!WIFEXITED(status) || WEXITSTATUS(status))
        return 1;
    puts("SYSCALL-ATTACK API: PASS 2/2 rejection checks");

    for (unsigned round = 1; round <= rounds; round++) {
        memset(&output, 0, sizeof(output));
        errno = 0;
        long rc = syscall(SYS_ioctl, fd, PV_SYSCALL_PROBE, &output);
        if (rc != 0 || output.version != 1 || output.count != 4) {
            fprintf(stderr, "SYSCALL-ATTACK FAIL round=%u rc=%ld errno=%d "
                    "version=%llu count=%llu\n", round, rc, errno,
                    (unsigned long long)output.version,
                    (unsigned long long)output.count);
            return 1;
        }
        for (unsigned i = 0; i < 4; i++) {
            const struct pv_access_result *r = &output.results[i];
            if (r->cause != causes[i] || r->before > UINT8_MAX ||
                r->before != r->after || (i == 0 && r->before != 0x5a)) {
                fprintf(stderr, "SYSCALL-ATTACK FAIL %s round=%u cause=%llu "
                        "expected=%llu before=%llu after=%llu\n", names[i], round,
                        (unsigned long long)r->cause,
                        (unsigned long long)causes[i],
                        (unsigned long long)r->before,
                        (unsigned long long)r->after);
                return 1;
            }
            printf("SYSCALL-ATTACK PASS %s round=%u cause=%llu bytes=unchanged\n",
                   names[i], round, (unsigned long long)r->cause);
            passed++;
        }
    }
    if (close(fd))
        die("close");
    printf("SYSCALL-ATTACK SUMMARY: PASS %u/12 checks (3 rounds x 4 cases)\n", passed);
    return passed == 12 ? 0 : 1;
}
