/* Test-only x86_64 seccomp fixture for Rust std entropy fallbacks. */
#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 3) return 2;
    const int flags_mode = strcmp(argv[1], "old-flags") == 0;
    if (!flags_mode && strcmp(argv[1], "enosys") != 0) return 2;
    struct sock_filter flags[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_getrandom, 0, 3),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[2])),
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 4, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EINVAL),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_filter unavailable[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_getrandom, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | ENOSYS),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)
    };
    struct sock_fprog program = {
        .len = flags_mode ? sizeof(flags)/sizeof(flags[0]) : sizeof(unavailable)/sizeof(unavailable[0]),
        .filter = flags_mode ? flags : unavailable
    };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program)) {
        perror("seccomp"); return 3;
    }
    char byte;
    errno = 0;
    if (syscall(SYS_getrandom, &byte, 1, 4) != -1 || errno != (flags_mode ? EINVAL : ENOSYS)) return 4;
    printf("FILTER VERIFIED %s\n", argv[1]); fflush(stdout);
    execvp(argv[2], argv+2);
    perror("execvp"); return 5;
}
