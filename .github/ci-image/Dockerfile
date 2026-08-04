# Toolchain image for the modern CI tier.
#
# Exists so that `make check-ci` and the CI jobs stop re-running the same
# apt-get install on every invocation. The Makefile used to carry the note
# "Slower than a host build because it installs packages each time (~40s).
# That is the price of not maintaining a second distro." That price was worth
# paying while this repository maintained no images; it already maintains the
# GCC 4.8.5 mirror, so the calculus changed.
#
# The image IS the pin. Versions live here rather than being re-listed in each
# workflow job, so an Ubuntu image refresh cannot quietly change what the gates
# check, and local and CI cannot drift apart -- which is exactly how the
# fidelity tier came to pass locally while failing in CI.
#
# tr_TR.UTF-8 is generated here rather than at run time. Without it the
# locale-independence test (L3-CPP-052) finds setlocale returning NULL and
# downgrades itself to a warning, so the gate silently checks less.
#
# Rebuild and push when a pinned version changes -- tags are dates, never
# `latest`, so a run always names the toolchain it used. A same-day rebuild
# takes a `.N` suffix rather than overwriting the tag, because a tag that
# changes meaning makes an old CI log impossible to interpret:
#
#   podman build -t ghcr.io/joey-huckabee/bfm-ci:YYYY-MM-DD \
#       -f .github/ci-image/Dockerfile .github/ci-image
#   podman push ghcr.io/joey-huckabee/bfm-ci:YYYY-MM-DD
#
# Then update CI_IMAGE in cpp/Makefile and the `container:` references in
# .github/workflows/cpp-ci.yml together, and make the package public -- it
# lives in a user namespace, so a workflow's GITHUB_TOKEN has no implicit read
# access to it.
FROM docker.io/library/ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Pinned by explicit version rather than taking the image defaults: Ubuntu
# 24.04 defaults to g++-13 and clang-tidy-18, and the gates deliberately use
# the newer g++-14 and clang-tidy-20 that the same repositories provide.
#
# gcc-14 is listed separately from g++-14 and is not redundant: the g++-14
# package alone leaves no usable `cc`, and the vendored SQLite amalgamation is
# C. Its absence broke the build the first time a C translation unit landed.
#
# libclang-rt-20-dev is likewise not redundant, and it is the reason
# --no-install-recommends needs care here. It carries the sanitizer runtimes
# the fuzz targets link against, and it arrives only as a recommendation one
# level down:
#
#   clang-20 -Depends-> libclang-common-20-dev -Recommends-> libclang-rt-20-dev
#
# The bare `apt-get install` this image replaced therefore pulled it in by
# accident. Built without it, every other tier linked fine and only the fuzz
# targets failed:
#
#   /usr/bin/ld: cannot find .../libclang_rt.asan_cxx.a: No such file
#
# Do not "verify" this by testing for that path -- it is clang's per-target
# fallback name and never exists on Ubuntu, which installs the runtimes as
# .../clang/20/lib/linux/libclang_rt.asan_cxx-x86_64.a. Verify by building the
# fuzz targets, which is the thing that actually has to work.
#
# Listed explicitly rather than dropping --no-install-recommends, so the image
# states what it needs instead of inheriting it by luck.
#
# git is here for actions/checkout, which runs *inside* this image once the
# workflow jobs declare it as their `container:`. Without git the action still
# succeeds, but silently falls back to downloading a REST tarball -- a degraded
# path with no repository metadata, which would quietly break anything that
# later needs history.
#
# ccache backs the vendored SQLite object only; see CCACHE in cpp/Makefile for
# why it is scoped that narrowly.
#
# curl and unzip are for the SonarCloud job, which downloads the scanner CLI.
# They are here so that workflow can run in this image too: it was the last one
# still apt-installing its own toolchain, which meant SonarCloud analysed a
# compilation built by a different compiler from the one CI verifies.
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        g++-14 \
        gcc-14 \
        make \
        clang-20 \
        clang-tidy-20 \
        libclang-rt-20-dev \
        cppcheck \
        valgrind \
        bear \
        ccache \
        git \
        curl \
        unzip \
        locales \
        ca-certificates && \
    locale-gen tr_TR.UTF-8 && \
    rm -rf /var/lib/apt/lists/*

# Recorded so `docker inspect` answers "what is this?" without hunting for the
# Dockerfile, and so GitHub links the package to this repository.
LABEL org.opencontainers.image.source=https://github.com/joey-huckabee/background-file-mover
LABEL org.opencontainers.image.description="Toolchain for the Background File Mover modern CI tier (g++-14, clang-20, sanitizers, valgrind, cppcheck, bear)"
