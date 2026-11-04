/* Root-only, fixed-payload user-page probe; research instrumentation only. */
#include <linux/capability.h>
#include <linux/cpu.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/uaccess.h>
#include <asm/processor.h>
#include <asm/pgtable.h>

#include <asm/tlbflush.h>
struct pv_user_request {
    __u64 address;
    __u64 physical;
    __u64 cause;
};
#define PV_USER_PROBE _IOWR('V', 0x56, struct pv_user_request)
static DEFINE_MUTEX(pv_user_lock);

#include <asm/tlbflush.h>

static int pv_enable_alias_exec(pte_t *pte, unsigned long address, void *data)
{
    struct page *page = data;
    pte_t entry = ptep_get(pte);
    unsigned long flags = pte_val(entry);
    unsigned long required = _PAGE_PRESENT | _PAGE_READ;

    if ((flags & required) != required ||
        (flags & (_PAGE_USER | _PAGE_WRITE)) ||
        pte_pfn(entry) != page_to_pfn(page))
        return -EINVAL;

    set_pte_at(&init_mm, address, pte,
               __pte(flags | _PAGE_EXEC));
    return 0;
}

static int pv_check_pte(pte_t *pte, unsigned long address, void *data)
{
    unsigned long flags = pte_val(ptep_get(pte));
    unsigned long required = _PAGE_PRESENT | _PAGE_READ | _PAGE_EXEC;
    pr_info("PMP.Virt USER PTE: flags=%lx required=%lx user=%lx write=%lx\n", flags, required, flags & _PAGE_USER, flags & _PAGE_WRITE);
    (void)address;
    (void)data;
    if ((flags & required) != required || (flags & (_PAGE_USER | _PAGE_WRITE)))
        { pr_err("PMP.Virt USER EINVAL line=%d\n", __LINE__); return -EINVAL; }
    return 0;
}

static long pv_user_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
    struct pv_user_request req;
    struct vm_area_struct *vma;
    struct page *page = NULL;
    void *alias = NULL, *old_alias;
    pgprot_t prot;
    long rc;
    unsigned initial_failures;
    const u32 payload[2] = {0x02a00513, 0x00008067};
    (void)file;
    if (cmd != PV_USER_PROBE)
        return -ENOTTY;
    if (!capable(CAP_SYS_ADMIN))
        return -EPERM;
    if (!READ_ONCE(pv_boot_tests_done) || num_online_cpus() != 1)
        return -EBUSY;
    if (copy_from_user(&req, (void __user *)arg, sizeof(req)))
        return -EFAULT;
    if (!req.address || (req.address & (PAGE_SIZE - 1)) ||
        req.address > TASK_SIZE - PAGE_SIZE)
        { pr_err("PMP.Virt USER EINVAL line=%d\n", __LINE__); return -EINVAL; }
    if (mutex_lock_interruptible(&pv_user_lock))
        return -EINTR;
    mmap_read_lock(current->mm);
    vma = vma_lookup(current->mm, req.address);
    if (!vma || vma->vm_end - req.address < PAGE_SIZE ||
        (vma->vm_flags & (VM_READ | VM_EXEC)) != (VM_READ | VM_EXEC) ||
        (vma->vm_flags & (VM_WRITE | VM_SHARED | VM_IO | VM_PFNMAP))) {
        pr_err("PMP.Virt USER EINVAL line=%d\n", __LINE__);
        rc = -EINVAL;
        goto unlock_mm;
    }
    rc = get_user_pages(req.address, 1, 0, &page);
    if (rc != 1) {
        rc = rc < 0 ? rc : -EFAULT;
        page = NULL;
        goto unlock_mm;
    }
    /* Explicit S-stage RX/U=0 alias to THE SAME pinned physical frame.
     * Do not call set_memory_x on vmap: that API needs vm_struct.pages.
     */
    prot = __pgprot((pgprot_val(PAGE_KERNEL) | _PAGE_EXEC) & ~_PAGE_WRITE);
    alias = vmap(&page, 1, VM_MAP, prot);
    if (!alias) {
        rc = -ENOMEM;
        goto unlock_mm;
    }
    if (memcmp(alias, payload, sizeof(payload))) {
        pr_err("PMP.Virt USER EINVAL line=%d\n", __LINE__);
        rc = -EINVAL;
        goto unlock_mm;
    }
    rc = apply_to_page_range(&init_mm, (unsigned long)alias, PAGE_SIZE,
                            pv_enable_alias_exec, page);
    if (rc)
        goto unlock_mm;
    flush_tlb_all();
    rc = apply_to_page_range(&init_mm, (unsigned long)alias, PAGE_SIZE,
                            pv_check_pte, NULL);
    if (rc)
        goto unlock_mm;
    req.physical = page_to_phys(page);
    flush_icache_range((unsigned long)alias, (unsigned long)alias + 8);
    old_alias = code_alias;
    code_alias = alias;
    initial_failures = failures;
    probe("user same-page HS RX/U0 execute", alias, true, 1);
    req.cause = observed_cause;
    code_alias = old_alias;
    pr_info("PMP.Virt USER frame: user_va=%llx physical=%llx kernel_alias=%lx cause=%llu\n",
            (unsigned long long)req.address, (unsigned long long)req.physical,
            (unsigned long)alias, (unsigned long long)req.cause);
    rc = failures == initial_failures ? 0 : -EIO;
unlock_mm:
    if (alias)
        vunmap(alias);
    if (page)
        put_page(page);
    mmap_read_unlock(current->mm);
    mutex_unlock(&pv_user_lock);
    if (!rc && copy_to_user((void __user *)arg, &req, sizeof(req)))
        return -EFAULT;
    return rc;
}

static const struct file_operations pv_user_ops = {
    .owner = THIS_MODULE,
    .unlocked_ioctl = pv_user_ioctl,
};
static struct miscdevice pv_user_device = {
    .minor = MISC_DYNAMIC_MINOR,
    .name = "pvtest",
    .fops = &pv_user_ops,
    .mode = 0600,
};
static int __init pv_user_init(void)
{
    return misc_register(&pv_user_device);
}
device_initcall(pv_user_init);
