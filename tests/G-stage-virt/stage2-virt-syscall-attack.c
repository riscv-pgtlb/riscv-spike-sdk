// SPDX-License-Identifier: GPL-2.0-only
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

#include <asm/stage2_virt_test.h>

#define TEST_DEVICE "/dev/stage2_virt_test"

static void die(const char *what)
{
	perror(what);
	exit(EXIT_FAILURE);
}

static void reject(int fd, void *output, int expected, const char *name)
{
	errno = 0;
	long rc = syscall(SYS_ioctl, fd, STAGE2_VIRT_TEST_IOC_ATTACK_PROBE,
			  output);
	if (rc != -1 || errno != expected) {
		fprintf(stderr, "STAGE2-SYSCALL-ATTACK FAIL %s rc=%ld errno=%d expected=%d\n",
			name, rc, errno, expected);
		exit(EXIT_FAILURE);
	}
}

int main(void)
{
	struct stage2_virt_attack_result output;
	unsigned int passed = 0;
	int status;

	setvbuf(stdout, NULL, _IONBF, 0);
	if (sysconf(_SC_PAGESIZE) != 4096 || geteuid() != 0) {
		fputs("STAGE2-SYSCALL-ATTACK FAIL requires root and 4 KiB pages\n", stderr);
		return EXIT_FAILURE;
	}
	int fd = open(TEST_DEVICE, O_RDWR | O_CLOEXEC);
	if (fd < 0)
		die("open " TEST_DEVICE);

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
		return EXIT_FAILURE;
	puts("STAGE2-SYSCALL-ATTACK API: PASS 2/2 rejection checks");

	for (unsigned int round = 1; round <= 3; round++) {
		memset(&output, 0, sizeof(output));
		errno = 0;
		long rc = syscall(SYS_ioctl, fd,
				  STAGE2_VIRT_TEST_IOC_ATTACK_PROBE, &output);
		if (rc || output.version != 1 || output.count != 1 ||
		    output.cause != 15 || output.before != 0x5a ||
		    output.after != output.before) {
			fprintf(stderr, "STAGE2-SYSCALL-ATTACK FAIL round=%u rc=%ld errno=%d version=%llu count=%llu cause=%llu before=%llu after=%llu\n",
				round, rc, errno,
				(unsigned long long)output.version,
				(unsigned long long)output.count,
				(unsigned long long)output.cause,
				(unsigned long long)output.before,
				(unsigned long long)output.after);
			return EXIT_FAILURE;
		}
		printf("STAGE2-SYSCALL-ATTACK PASS VS-store round=%u cause=15 bytes=unchanged\n",
		       round);
		passed++;
	}
	if (close(fd))
		die("close");
	printf("STAGE2-SYSCALL-ATTACK SUMMARY: PASS %u/3 checks (3 rounds x 1 case)\n",
	       passed);
	return passed == 3 ? EXIT_SUCCESS : EXIT_FAILURE;
}
