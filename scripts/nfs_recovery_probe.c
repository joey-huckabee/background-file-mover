/* Fixture-only retained-FD probe, never linked into the Rust service. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
static void fail(const char *s) { perror(s); exit(1); }
static void wait_for(const char *p) {
    struct timespec pause = {0, 1000000};
    unsigned budget = 120000;
    while (access(p, F_OK)) {
        if (errno != ENOENT || !budget--) fail("rendezvous/deadline");
        nanosleep(&pause, NULL);
    }
}
static void marker(const char *p, int fd) {
    FILE *f = fopen(p, "wx");
    if (!f) fail("marker");
    fprintf(f, "%ld %d\n", (long)getpid(), fd);
    if (fclose(f)) fail("marker close");
}
int main(int argc, char **argv) {
    if (argc != 7) return 2;
    int fd = open(argv[1], O_RDWR|O_CREAT|O_EXCL, 0600);
    if (fd < 0) fail("open");
    marker(argv[2], fd); wait_for(argv[3]);
    char data[4096], readback[4096]; struct stat before, after;
    memset(data, 'A', sizeof(data));
    if (pwrite(fd, data, sizeof(data), 0) != sizeof(data) || fsync(fd)) fail("initial write/sync");
    if (fstat(fd, &before)) fail("initial fstat");
    marker(argv[4], fd); wait_for(argv[5]);
    memset(data, 'B', sizeof(data));
    if (pwrite(fd, data, sizeof(data), 0) != sizeof(data) || fsync(fd)) fail("recovered write/sync");
    if (fstat(fd, &after) || before.st_dev != after.st_dev || before.st_ino != after.st_ino || after.st_size != 4096) fail("identity/size");
    if (pread(fd, readback, sizeof(readback), 0) != sizeof(readback) || memcmp(data, readback, sizeof(data))) fail("readback");
    if (close(fd)) fail("close");
    marker(argv[6], -1);
    puts("retained FD write/fsync/readback/identity passed");
    return 0;
}
