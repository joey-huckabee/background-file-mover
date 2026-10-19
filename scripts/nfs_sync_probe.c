/* Disposable OS fixture only; never linked into or shipped with the mover. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
static void fail(const char *what) { perror(what); exit(1); }
int main(int argc, char **argv) {
    if (argc != 5) return 2;
    const int directory = strcmp(argv[1], "directory") == 0;
    int fd = open(argv[2], directory ? O_RDONLY|O_DIRECTORY : O_RDWR|O_CREAT|O_EXCL, 0600);
    if (fd < 0) fail("open");
    if (!directory && strcmp(argv[1], "clean") == 0 && fsync(fd)) fail("prepare clean fsync");
    FILE *ready = fopen(argv[3], "wx");
    if (!ready) fail("ready");
    fprintf(ready, "%ld %d\n", (long)getpid(), fd);
    if (fclose(ready)) fail("ready close");
    struct timespec pause = {0, 1000000};
    unsigned budget = 120000;
    while (access(argv[4], F_OK)) {
        if (errno != ENOENT || !budget--) fail("go/deadline");
        nanosleep(&pause, NULL);
    }
    if (!directory && strcmp(argv[1], "clean") != 0) {
        if (strcmp(argv[1], "chmod") == 0) {
            char *data = calloc(1048576, 1);
            if (!data) fail("calloc");
            for (int i = 0; i < 2; ++i)
                if (write(fd, data, 1048576) != 1048576) fail("large write");
            free(data);
            if (write(fd, "0123456789abcdefg", 17) != 17) fail("tail write");
            printf("fchmod enter %d\n", fd); fflush(stdout);
            if (fchmod(fd, 0400)) fail("fchmod");
            printf("fchmod returned 0\n"); fflush(stdout);
        } else {
            char data[4096]; memset(data, 'S', sizeof(data));
            if (write(fd, data, sizeof(data)) != sizeof(data)) fail("write");
        }
    }
    printf("fsync enter %d\n", fd); fflush(stdout);
    if (fsync(fd)) fail("fsync");
    printf("fsync returned 0\n"); fflush(stdout);
    if (close(fd)) fail("close");
    return 0;
}
