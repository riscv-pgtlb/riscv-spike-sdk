// SPDX-License-Identifier: GPL-2.0-only
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <asm/stage2_virt_test.h>

#define TEST_DEVICE "/dev/stage2_virt_test"
#define VU_BEFORE_VALUE UINT8_C(0x5a)
#define VU_AFTER_VALUE  UINT8_C(0xa5)

static int fail(const char *operation)
{
	fprintf(stderr, "Stage2Virt Guest userspace FAIL: %s: %s\n",
		operation, strerror(errno));
	return EXIT_FAILURE;
}

static int store_and_verify(volatile uint8_t *page, uint8_t value)
{
	__atomic_store_n(page, value, __ATOMIC_SEQ_CST);
	if (__atomic_load_n(page, __ATOMIC_SEQ_CST) != value) {
		errno = EIO;
		return -1;
	}
	return 0;
}

int main(void)
{
	struct stage2_virt_test_info info = { 0 };
	struct stage2_virt_test_value value = { 0 };
	volatile uint8_t *page = MAP_FAILED;
	long host_page_size;
	bool session_active = false;
	int fd = -1;
	int status = EXIT_FAILURE;

	host_page_size = sysconf(_SC_PAGESIZE);
	if (host_page_size <= 0)
		return fail("query page size");

	fd = open(TEST_DEVICE, O_RDWR | O_CLOEXEC);
	if (fd < 0)
		return fail("open " TEST_DEVICE);

	if (ioctl(fd, STAGE2_VIRT_TEST_IOC_GET_INFO, &info) < 0) {
		fail("GET_INFO ioctl");
		goto out;
	}
	if (info.size != (uint64_t)host_page_size ||
	    info.gpa % (uint64_t)host_page_size) {
		errno = EPROTO;
		fail("validate test page information");
		goto out;
	}

	page = mmap(NULL, info.size, PROT_READ | PROT_WRITE,
		    MAP_SHARED, fd, 0);
	if (page == MAP_FAILED) {
		fail("mmap test page");
		goto out;
	}

	printf("Stage2Virt Guest test page: GPA=0x%016" PRIx64
	       " size=%" PRIu64 "\n", (uint64_t)info.gpa,
	       (uint64_t)info.size);

	if (ioctl(fd, STAGE2_VIRT_TEST_IOC_BEGIN) < 0) {
		fail("BEGIN ioctl");
		goto out;
	}
	session_active = true;

	if (store_and_verify(page, VU_BEFORE_VALUE) < 0) {
		fail("VU first write");
		goto out;
	}
	printf("Stage2Virt Guest VU BEFORE PASS: GPA=0x%016" PRIx64
	       " value=0x%02x\n", (uint64_t)info.gpa, VU_BEFORE_VALUE);

	value.expected = VU_BEFORE_VALUE;
	if (ioctl(fd, STAGE2_VIRT_TEST_IOC_VS_PROBE, &value) < 0) {
		fail("VS_PROBE ioctl");
		goto out;
	}
	if (__atomic_load_n(page, __ATOMIC_SEQ_CST) != VU_BEFORE_VALUE) {
		errno = EIO;
		fail("verify page after VS probe");
		goto out;
	}
	printf("Stage2Virt Guest VS PROBE PASS: GPA=0x%016" PRIx64
	       " expected-access-fault\n", (uint64_t)info.gpa);

	if (store_and_verify(page, VU_AFTER_VALUE) < 0) {
		fail("VU second write");
		goto out;
	}
	printf("Stage2Virt Guest VU AFTER PASS: GPA=0x%016" PRIx64
	       " value=0x%02x\n", (uint64_t)info.gpa, VU_AFTER_VALUE);

	memset(&value, 0, sizeof(value));
	value.expected = VU_AFTER_VALUE;
	if (ioctl(fd, STAGE2_VIRT_TEST_IOC_COMPLETE, &value) < 0) {
		fail("COMPLETE ioctl");
		goto out;
	}
	session_active = false;

	printf("Stage2Virt Guest VU-VS-VU SAME-PAGE PASS: "
	       "GPA=0x%016" PRIx64 "\n", (uint64_t)info.gpa);
	status = EXIT_SUCCESS;

out:
	if (session_active && ioctl(fd, STAGE2_VIRT_TEST_IOC_ABORT) < 0)
		fprintf(stderr, "Stage2Virt Guest userspace ABORT failed: %s\n",
			strerror(errno));
	if (page != MAP_FAILED && munmap((void *)page, info.size) < 0) {
		fprintf(stderr, "Stage2Virt Guest userspace munmap failed: %s\n",
			strerror(errno));
		status = EXIT_FAILURE;
	}
	if (close(fd) < 0) {
		fprintf(stderr, "Stage2Virt Guest userspace close failed: %s\n",
			strerror(errno));
		status = EXIT_FAILURE;
	}
	return status;
}
