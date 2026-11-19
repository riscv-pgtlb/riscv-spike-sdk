#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

struct pv_user_request {
    uint64_t address, physical, cause;
};
#define PV_USER_PROBE _IOWR('V', 0x56, struct pv_user_request)
static void die(const char *s) { perror(s); exit(1); }

int main(void)
{
    long size = sysconf(_SC_PAGESIZE);
    const uint32_t payload[] = {0x02a00513, 0x00008067};
    void *page;
    int fd;
    struct pv_user_request req = {0};
    unsigned long (*fn)(void);
    unsigned long value;
    if (size != 4096) {
        fputs("FAIL: expected 4 KiB pages\n", stderr);
        return 1;
    }
    page = mmap(NULL, size, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (page == MAP_FAILED) die("mmap");
    memcpy(page, payload, sizeof(payload));
    puts("User wrote fixed instructions into RW/NX anonymous page");
    if (mprotect(page, size, PROT_READ | PROT_EXEC)) die("mprotect RX");
    __builtin___clear_cache(page, (char *)page + sizeof(payload));
    fn = (unsigned long (*)(void))page;
    value = fn();
    if (value != 42) {
        fprintf(stderr, "FAIL U execution returned %lu\n", value);
        return 1;
    }
    printf("PASS U execute before HS probe: value=%lu VA=%p\n", value, page);
    fd = open("/dev/pvtest", O_RDWR | O_CLOEXEC);
    if (fd < 0) die("open /dev/pvtest");
    req.address = (uintptr_t)page;
    if (ioctl(fd, PV_USER_PROBE, &req)) die("ioctl HS probe");
    if (req.cause != 1) {
        fprintf(stderr, "FAIL HS cause=%llu\n", (unsigned long long)req.cause);
        return 1;
    }
    printf("PASS HS denied same physical page: PA=0x%llx cause=%llu\n",
           (unsigned long long)req.physical, (unsigned long long)req.cause);
    value = fn();
    if (value != 42) {
        fprintf(stderr, "FAIL second U execution returned %lu\n", value);
        return 1;
    }
    puts("PASS U execute after HS probe: value=42");
    puts("PMP.Virt USER SUMMARY: PASS U-success / HS-access-fault / U-success");
    close(fd);
    munmap(page, size);
    return 0;
}
