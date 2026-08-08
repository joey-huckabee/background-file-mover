# Background File Mover — C++ build (ADR-0005)
# Target toolchain: GCC 4.8.5 on SLES 12 SP5. Keep everything C++11-clean.

CXX      ?= g++
CPPFLAGS += -Iinclude -isystem third_party

# --- Memory-safety instrumentation (modern toolchains; CI jobs) ---------
# Usage: make check SANITIZE=1     (AddressSanitizer + UBSan + LeakSanitizer)
#        make check-valgrind       (Valgrind memcheck, error on any finding)
# GCC 4.8 has only partial ASan and no LSan, so sanitizer jobs run on the
# modern compiler; the code under test is identical because the source is
# strictly C++11-conformant and compiled from one body (ADR-0001).
#
# This block must precede BUILD_DIR, which keys on TOOLCHAIN — make expands
# target patterns as it parses, so a later edit to TOOLCHAIN would not reach
# the rules below.
SANITIZE ?= 0
THREAD   ?= 0
ifeq ($(SANITIZE),1)
# -Wmaybe-uninitialized is disabled for this tier only. Under -O1 plus
# instrumentation it false-positives deep inside libstdc++ — GCC 13 reports
# it against <regex> internals reached through Catch2, in code we neither
# wrote nor include directly. The sanitizers perform the real, runtime
# uninitialized-read detection that this diagnostic only approximates, so
# nothing is lost by turning it off precisely where it is unreliable.
#
# This is NOT the same as the two per-object exemptions that api_codec.o and
# test_api_codec.o once carried: those were specific to picojson and went
# away with it (ADR-0006). This one is about the standard library and must
# stay. Removing it breaks the sanitizer tier on GCC 13 while leaving GCC 11
# green, which is a confusing way to find out.
CXXFLAGS ?= -std=c++11 -Wall -Wextra -Werror -O1 -g \
            -Wno-maybe-uninitialized \
            -fsanitize=address,undefined -fno-omit-frame-pointer \
            -fno-sanitize-recover=all
# Kept separately so the vendored C unit is instrumented by the same tier.
# Linking uninstrumented C into a sanitized binary is not merely a coverage
# gap: TSan reports races it cannot see the synchronisation for, as false
# positives against code that is actually correct.
SAN_FLAGS := -fsanitize=address,undefined -fno-omit-frame-pointer \
             -fno-sanitize-recover=all
TIER := asan
else ifeq ($(THREAD),1)
# ThreadSanitizer (L2-ARC-008). A SEPARATE tier, not an additional flag: TSan
# and ASan cannot coexist in one binary, and their shadow-memory layouts
# conflict. Its own build directory keeps the artifacts apart.
#
# Data races are the failure class a passing suite is least likely to catch —
# a race can sit in the tree for years and surface only under a scheduler the
# test machine never produces. Worth its own gate as soon as the first thread
# exists.
CXXFLAGS ?= -std=c++11 -Wall -Wextra -Werror -O1 -g \
            -Wno-maybe-uninitialized \
            -fsanitize=thread -fno-omit-frame-pointer \
            -fno-sanitize-recover=all
SAN_FLAGS := -fsanitize=thread -fno-omit-frame-pointer \
             -fno-sanitize-recover=all
TIER := tsan
else
CXXFLAGS ?= -std=c++11 -Wall -Wextra -Werror -O2 -g
SAN_FLAGS :=
TIER := default
endif

# Object files are keyed on the toolchain that produced them, so the tiers
# cannot clobber one another. Running the WSL build and then the gcc:4.8
# container build over a shared directory previously left a glibc-2.34 binary
# in place for the container to execute, which fails with a wall of
# "GLIBC_2.xx not found" and reads as a code fault rather than a stale artifact.
#
# Override per invocation when needed: make BUILD_DIR=/somewhere/else
TOOLCHAIN ?= $(shell $(CXX) -dumpmachine 2>/dev/null)-$(shell $(CXX) -dumpversion 2>/dev/null)-$(TIER)
BUILD_DIR ?= build/$(TOOLCHAIN)

LIB_SRC  := src/job.cpp src/json.cpp src/api_codec.cpp src/config.cpp src/rename_template.cpp src/http_parser.cpp src/store.cpp src/fsops.cpp src/mover.cpp src/manager.cpp src/server.cpp src/router.cpp src/http_service.cpp src/service.cpp src/singleton.cpp
LIB_OBJ  := $(patsubst src/%.cpp,$(BUILD_DIR)/src/%.o,$(LIB_SRC))

# --- Vendored SQLite (ADR-0010, ADR-0004) --------------------------------
# The amalgamation is C, not C++, so it needs its own compiler and its own
# flags. It is deliberately NOT in LIB_SRC: that variable drives clang-tidy,
# cppcheck, clang-format, coverage, and the fuzz targets, and none of them
# should be pointed at 250 kLOC of third-party code we are forbidden to edit.
CC ?= cc
SQLITE_SRC := third_party/sqlite/sqlite3.c
SQLITE_OBJ := $(BUILD_DIR)/third_party/sqlite3.o

# Compile-time configuration. Each of these is a decision, not a default:
#   THREADSAFE=1          serialized mode; C4 introduces the first threads and
#                         the store is reached from all of them.
#   OMIT_LOAD_EXTENSION   removes sqlite3_load_extension entirely. A database
#                         file must never be able to make this process dlopen
#                         anything (docs/CYBERSECURITY.md).
#   DQS=0                 disables the double-quoted-string misfeature, where a
#                         mistyped identifier silently degrades into a string
#                         literal instead of erroring.
#   DEFAULT_MEMSTATUS=0   drops per-allocation accounting we never read.
#   ENABLE_API_ARMOR      validates arguments at the API boundary rather than
#                         invoking undefined behaviour on misuse.
SQLITE_DEFS := -DSQLITE_THREADSAFE=1 \
               -DSQLITE_OMIT_LOAD_EXTENSION \
               -DSQLITE_DQS=0 \
               -DSQLITE_DEFAULT_MEMSTATUS=0 \
               -DSQLITE_ENABLE_API_ARMOR

# -Werror is kept, unqualified -- this is NOT a warning exemption of the kind
# the note at the foot of this file prohibits. Two deliberate differences from
# CXXFLAGS, both measured in the gcc:4.8 container (see cpp/VENDORED.md):
#
#   -fno-strict-aliasing  sqlite3.c writes digit pairs through a u16* cast in
#                         sqlite3Int64ToText and sqlite3FpDecode. This is the
#                         correct fix, not -Wno-strict-aliasing: the warning is
#                         a symptom, and what actually matters is denying the
#                         optimizer the aliasing assumption the code breaks.
#   no -Wextra            -Wunused-parameter fires on sqlite3_setlk_timeout.
#                         -Wextra is a style gate for code we control; we are
#                         forbidden to edit this file (ADR-0004), so enforcing
#                         it here could only ever be satisfied by a patch file.
#
# Verified clean under GCC 4.8.5, GCC 11, and clang with exactly these flags.
SQLITE_CFLAGS ?= -O2 -g -Wall -Werror -fno-strict-aliasing $(SAN_FLAGS)

# The link line for every binary here, not just SQLite's needs. It was called
# SQLITE_LDLIBS while SQLite was the only thing driving it, and kept that name
# after it stopped being true.
#
# -lrt is for clock_gettime, which C4's manager calls for its monotonic clock.
# On the glibc that ships with the deployment target it lives in librt; it moved
# into libc proper in later versions, where -lrt resolves to a stub and costs
# nothing. Omitting it links fine on every modern tier and fails only on GCC
# 4.8.5 -- which is exactly what happened, and exactly what that tier is for.
LINK_LIBS := -lpthread -lm -lrt

# ccache, applied to THIS object and nothing else.
#
# sqlite3.c takes 48.8s to compile against 1.35s for a typical C++ file, and
# check-ci rebuilds it five or six times per run -- once per tier, plus after
# each clean-all. It is also the one source here that never changes: ADR-0004
# forbids editing vendored files, so every one of those rebuilds produces a
# byte-identical object. That is the ideal case for a compiler cache.
#
# Deliberately NOT applied to the project's own sources. The win there is a
# second or two, and the coverage tier compiles with --coverage, where ccache
# has to get .gcno placement right for gcov to resolve anything. That is a real
# risk taken for no measurable gain, and this project's coverage reporting has
# already been broken once by a path-resolution subtlety.
#
# Empty when ccache is not installed, so the rule degrades to a plain compile.
CCACHE ?= $(shell command -v ccache 2>/dev/null)

# Parsers that sit on untrusted input and must classify characters with
# explicit ranges (L3-CPP-052). config.cpp is deliberately NOT here: it reads a
# trusted local file and its one strtoul call is guarded token-wise by
# parse_uint (L3-CPP-038).
PARSER_SRC := src/http_parser.cpp src/json.cpp

TEST_SRC := tests/test_main.cpp tests/test_job.cpp tests/test_json.cpp tests/test_api_codec.cpp tests/test_config.cpp tests/test_rename_template.cpp tests/test_http_parser.cpp tests/test_sqlite_vendor.cpp tests/test_store.cpp tests/test_fsops.cpp tests/test_mover.cpp tests/test_manager.cpp tests/test_server.cpp tests/test_connection_server.cpp tests/test_router.cpp tests/test_http_service.cpp tests/test_service.cpp tests/test_singleton.cpp
TEST_OBJ := $(patsubst tests/%.cpp,$(BUILD_DIR)/tests/%.o,$(TEST_SRC))

TEST_BIN := $(BUILD_DIR)/filemover_tests

.PHONY: all check clean clean-all check-valgrind toolchain \
        fuzz fuzz-run fuzz-corpus coverage tidy format-check

all: $(TEST_BIN)

# Header dependency tracking. Not a convenience -- a correctness requirement.
#
# Without this, make rebuilds a .o only when its .cpp is newer, so editing a
# header leaves every object that included it stale. Adding a declaration is
# survivable; changing a struct's LAYOUT is not. The C4 retry fields grew
# Config by twelve bytes, and a stale test object kept the old size: the test
# put the small Config on its stack, and load_config_from_string assigned the
# large one over it -- straight past the end. That surfaced as "stack smashing
# detected" in a test not touched in three milestones, an ODR violation
# manufactured by the build system rather than by any source file.
#
# -MMD writes a .d beside each .o listing the headers it included; -MP adds a
# phony target per header so a DELETED header does not wedge make with "no
# rule to make target". The generated files are included at the foot of this
# file, guarded with '-' so a first build (when none exist yet) is clean.
DEPFLAGS := -MMD -MP

$(BUILD_DIR)/src/%.o: src/%.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(BUILD_DIR)/tests/%.o: tests/%.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

# A pattern rule, not an explicit path, so the coverage tier reuses this recipe
# instead of duplicating it. The stem is the build directory, which is how one
# rule serves build/<toolchain>/ and build/coverage/ alike.
%/third_party/sqlite3.o: $(SQLITE_SRC)
	@mkdir -p $(dir $@)
	$(CCACHE) $(CC) $(SQLITE_DEFS) $(SQLITE_CFLAGS) -c $< -o $@

$(TEST_BIN): $(LIB_OBJ) $(TEST_OBJ) $(SQLITE_OBJ)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LINK_LIBS)

check: $(TEST_BIN)
	$(TEST_BIN) --use-colour no

# The daemon itself. src/main.cpp is deliberately NOT in LIB_SRC: it defines
# main(), and the test binary already has one from Catch2. Keeping it out of
# that list is what lets both link, and is why the entry point is thin -- every
# part of it worth testing lives in service.cpp, which IS in LIB_SRC.
DAEMON_BIN := $(BUILD_DIR)/filemover
DAEMON_OBJ := $(BUILD_DIR)/src/main.o

.PHONY: daemon
daemon: $(DAEMON_BIN)

$(DAEMON_BIN): $(LIB_OBJ) $(DAEMON_OBJ) $(SQLITE_OBJ)
	$(CXX) $(CXXFLAGS) $^ -o $@ $(LINK_LIBS)

# Removes only this toolchain's artifacts; other tiers are left intact.
clean:
	rm -rf $(BUILD_DIR)

# Removes every tier.
clean-all:
	rm -rf build

# Print the resolved build directory — useful when a tier's artifacts need
# locating from CI or a container.
toolchain:
	@echo "CXX=$(CXX) TIER=$(TIER) BUILD_DIR=$(BUILD_DIR)"

# Print every tool version that affects a build or a gate. CI runs this too,
# so a runner-image upgrade shows up as a visible diff in the log rather than
# as an unexplained warning in an unrelated job.
#
# The deployment target is GCC 4.8.5 on SLES 12 SP5. The modern toolchain
# below is an *instrument*, not a target: it hosts the sanitizers, libFuzzer,
# and clang-tidy that GCC 4.8 cannot. Its version still has to be pinned,
# because analysis tools change what they report between releases.
#
# Each line guards on `command -v` before running the tool. The obvious form,
#   tool --version | head -1 || echo MISSING
# can never print MISSING: the exit status of a pipeline is the *last*
# command's, and head succeeds on empty input. A missing tool printed a blank
# line instead -- silent, in the one target whose whole purpose is visibility.
# Found when the CI jobs moved into a container that has gcov-14 but no
# unversioned gcov.
versions:
	@echo "--- host toolchain (CI pins ubuntu-24.04 / g++-14 / clang-tidy-20) ---"
	@printf '%-12s ' "g++";        (command -v $(CXX) >/dev/null 2>&1 && $(CXX) --version 2>/dev/null | head -1) || echo "MISSING"
	@printf '%-12s ' "make";       (command -v make >/dev/null 2>&1 && make --version 2>/dev/null | head -1) || echo "MISSING"
	@printf '%-12s ' "cc";         (command -v $(CC) >/dev/null 2>&1 && $(CC) --version 2>/dev/null | head -1) || echo "MISSING"
	@printf '%-12s ' "clang++";    (command -v $(FUZZ_CXX) >/dev/null 2>&1 && $(FUZZ_CXX) --version 2>/dev/null | head -1) || echo "MISSING"
	@# $(TIDY), not a bare `clang-tidy`: the pinned binary is clang-tidy-20 and
	@# the unversioned name is a different package that need not be installed.
	@# Reporting the wrong one made this line read MISSING while the gate it
	@# describes was working.
	@printf '%-12s ' "clang-tidy"; (command -v $(TIDY) >/dev/null 2>&1 && $(TIDY) --version 2>/dev/null | grep -i 'version' | head -1) || echo "MISSING"
	@printf '%-12s ' "valgrind";   (command -v valgrind >/dev/null 2>&1 && valgrind --version 2>/dev/null) || echo "MISSING"
	@printf '%-12s ' "cppcheck";   (command -v cppcheck >/dev/null 2>&1 && cppcheck --version 2>/dev/null) || echo "MISSING"
	@printf '%-12s ' "ccache";     (command -v ccache >/dev/null 2>&1 && ccache --version 2>/dev/null | head -1) || echo "MISSING (sqlite3.o will rebuild each tier)"
	@printf '%-12s ' "gcov";       (command -v $(GCOV) >/dev/null 2>&1 && $(GCOV) --version 2>/dev/null | head -1) || echo "MISSING"
	@echo "--- deployment target (fidelity tier) ---"
	@# The guard is load-bearing now that CI jobs run *inside* a container: there
	@# is no container engine in there, and without it this line printed a blank
	@# version rather than saying why -- in the one target whose entire job is
	@# making the toolchain visible.
	@printf '%-12s ' "gcc 4.8.5";  (command -v $(CI_ENGINE) >/dev/null 2>&1 && \
	    $(CI_ENGINE) run --rm $(GCC48_IMAGE) g++ --version 2>/dev/null | head -1) || \
	    echo "no container engine here (expected inside a CI container)"

check-valgrind: $(TEST_BIN)
	valgrind --tool=memcheck --leak-check=full --show-leak-kinds=all \
	  --errors-for-leak-kinds=all --error-exitcode=1 \
	  $(TEST_BIN) --use-colour no

# --- CI parity -----------------------------------------------------------
# Runs the modern tier in the same image CI uses, so a local run and a CI run
# are the same run. The host toolchain stays whatever the distro ships and is
# for the fast inner loop; this target is for "why does CI disagree with me".
#
# Slower than a host build because it installs packages each time (~40s). That
# is the price of not maintaining a second distro, and it is only paid when
# reproducing CI.
#
# --cap-add=SYS_PTRACE is required: LeakSanitizer uses ptrace, containers
# block it by default, and LSan then dies with a fatal error that looks like
# a test failure. GitHub's runner is not a container and does not need this.
# These must match .github/workflows/cpp-ci.yml. Tools are pinned by explicit
# version rather than taking the image defaults, so an Ubuntu image refresh
# cannot change what the gates check.
# A prebuilt toolchain image (.github/ci-image/Dockerfile), not bare ubuntu:24.04.
# This target used to apt-get install the toolchain on every invocation, and
# carried the note "That is the price of not maintaining a second distro."
# That price was right while this repository maintained no images; it already
# maintains the GCC 4.8.5 mirror, so the trade changed.
#
# Tagged by date, never `latest`, so a run always names the toolchain it used.
# Rebuild and repush when a pinned version changes -- see the Dockerfile.
CI_IMAGE  ?= ghcr.io/joey-huckabee/bfm-ci:2026-08-04

# Survives between check-ci runs, which is the entire point: the container is
# discarded on exit, so an in-container cache would start cold every time and
# save nothing. Lives outside the repository so `git clean` cannot wipe it.
CCACHE_HOST_DIR ?= $(HOME)/.cache/background-file-mover-ccache
CI_ENGINE ?= $(shell command -v podman >/dev/null 2>&1 && echo podman || echo docker)
CI_CXX    ?= g++-14
# The vendored SQLite amalgamation is C, so this image needs a C compiler too.
# It has none by default: `g++-14` alone leaves no `cc`, and the build failed
# with "make: cc: No such file or directory" the first time sqlite3.c was
# added. Pinned to match CI_CXX for the same reason every other tool here is
# pinned -- the runner's default `cc` is gcc-13, a different compiler from the
# g++-14 the C++ objects are built with.
CI_CC     ?= gcc-14
CI_GCOV   ?= gcov-14
CI_TIDY   ?= clang-tidy-20
CI_FUZZ   ?= clang++-20
# The package list moved into .github/ci-image/Dockerfile. It is deliberately
# not duplicated here: two copies of a pinned toolchain is how the pins drift.
# Parallel compilation for the CI tiers. Measured on a 16-core host: the
# default tier went from 97s to 52s from clean.
#
# Do not expect it to scale further. The vendored sqlite3.c is a single 9.5 MB
# translation unit that takes 48.8s on its own, against 1.35s for a typical C++
# file, so it *is* the critical path -- a parallel build is now almost exactly
# "compile sqlite3.c". Adding cores past that buys nothing.
#
# Verified deterministic across five consecutive builds from clean, which is
# the test that matters: a missing prerequisite surfaces under -j as an
# intermittent failure, never a reproducible one.
CI_JOBS   ?= $(shell nproc 2>/dev/null || echo 4)

# --- Deployment-fidelity tier (GCC 4.8.5) --------------------------------
# A MIRROR of docker.io/library/gcc:4.8, not that image directly.
#
# The upstream image was published in 2016 with a Docker manifest v2 *schema 1*.
# Modern Docker disables schema 1 by default, so the CI job died at the pull
# with "exit code 125" before compiling anything -- while the same tier passed
# locally, because podman still accepts schema 1. That divergence is exactly
# what this Makefile exists to prevent: local and CI must pull the same bytes.
# The mirror is the identical image republished with a v2s2 manifest.
#
# Schema 1 support is slated for removal outright, so re-pointing at the
# upstream tag is not a fix that survives.
GCC48_IMAGE ?= ghcr.io/joey-huckabee/gcc-4.8:4.8.5

# Runs the fidelity tier the way CI runs it. Previously this command lived only
# in prose -- CONTRIBUTING.md, CLAUDE.md, and cpp-ci.yml each spelled out their
# own docker/podman invocation, which is how CI ended up pulling a different
# image from the one developers pulled. One target, one image, both callers.
.PHONY: check-gcc48
check-gcc48:
	$(CI_ENGINE) run --rm -v $(CURDIR)/..:/src -w /src $(GCC48_IMAGE) \
	    sh -c "make -C cpp clean && make -C cpp -j$(CI_JOBS) check"

# The pre-push check: the gates whose LOCAL tool differs from CI's, run in the
# CI image with CI's tools. Minutes rather than the quarter-hour check-ci takes.
#
# Every tool a developer runs here is older than the one CI runs. Measured
# 2026-08-06 on Ubuntu 22.04 against the CI image (Ubuntu 24.04):
#
#     g++          11.4.0  vs  14.2.0
#     clang-tidy   14.0.0  vs  20.1.2
#     valgrind     3.18.1  vs  3.22.0
#     cppcheck      2.7    vs   2.13.0
#
# That matters because a passing local run can mean "my tool does not know
# about this check" rather than "this code is fine". It already happened once:
# clang-tidy 14 could not see misc-const-correctness, so `make tidy` was clean
# while CI failed with twenty errors from that one check.
#
# The compiler gap is the same hazard and has not bitten yet. The build is
# -Wall -Wextra -Werror, and GCC 12 through 14 added warnings that g++ 11
# cannot emit, so a local `make check` can pass on code CI refuses.
#
# Not a substitute for check-ci, which additionally runs the sanitizer,
# Valgrind, coverage and fuzz tiers. This is what to run before pushing.
.PHONY: verify-ci
verify-ci:
	@echo "Running the divergence-prone gates in $(CI_IMAGE) via $(CI_ENGINE)..."
	$(CI_ENGINE) run --rm -v $(CURDIR):/cpp -w /cpp $(CI_IMAGE) sh -c '\
	  echo "--- versions ---" && \
	  $(CI_CXX) --version | head -1 && \
	  $(CI_TIDY) --version | grep -i version | head -1 && \
	  echo "--- functional build and test on CI compiler ---" && \
	  make clean-all >/dev/null && \
	  bear -- make -j$(CI_JOBS) all CXX=$(CI_CXX) CC=$(CI_CC) && \
	  ./$$(make -s print-test-bin CXX=$(CI_CXX) CC=$(CI_CC)) --use-colour no && \
	  echo "--- clang-tidy ---" && \
	  make tidy TIDY=$(CI_TIDY) CXX=$(CI_CXX) CC=$(CI_CC)'
	@echo ""
	@echo "verify-ci OK. Note this leaves the build tree built with $(CI_CXX);"
	@echo "your next local 'make check' will rebuild against the host compiler."

# Prints the test binary path for the current toolchain, so a caller inside the
# container can run it without duplicating the BUILD_DIR derivation.
.PHONY: print-test-bin
print-test-bin:
	@echo $(TEST_BIN)

# Same, for the daemon. Used by scripts/assert-unit-valid.sh so the deployment
# gate does not hard-code a toolchain-specific build path.
.PHONY: print-daemon-bin
print-daemon-bin:
	@echo $(DAEMON_BIN)

.PHONY: check-ci
check-ci:
	@echo "Running the CI tiers in $(CI_IMAGE) via $(CI_ENGINE)..."
	@mkdir -p $(CCACHE_HOST_DIR)
	$(CI_ENGINE) run --rm --cap-add=SYS_PTRACE \
	    -v $(CCACHE_HOST_DIR):/ccache -e CCACHE_DIR=/ccache \
	    -v $(CURDIR):/cpp -w /cpp $(CI_IMAGE) sh -c '\
	      echo "--- versions ---" && \
	      $(CI_CXX) --version | head -1 && \
	      $(CI_TIDY) --version | grep -i version | head -1 && \
	      { locale -a 2>/dev/null | grep -qi "^tr_TR" || \
	        { echo "tr_TR.UTF-8 missing from $(CI_IMAGE); the L3-CPP-052 runtime check would only warn" >&2; \
	          exit 1; }; } && \
	      echo "--- vendored hashes ---" && sh scripts/verify-vendored.sh && \
	      echo "--- locale-free parsers ---" && \
	      sh scripts/assert-locale-free.sh $(PARSER_SRC) && \
	      echo "--- sql confinement ---" && \
	      sh scripts/assert-sql-confined.sh && \
	      echo "--- fd-relative filesystem access ---" && \
	      sh scripts/assert-fd-relative.sh && \
	      echo "--- no shell invocation ---" && \
	      sh scripts/assert-no-shell.sh && \
	      echo "--- no permission-based test failures ---" && \
	      sh scripts/assert-no-permission-tests.sh && \
	      echo "--- no timed condition waits ---" && \
	      sh scripts/assert-no-timed-condwait.sh && \
	      echo "--- manager mutex taken only through ManagerLock ---" && \
	      sh scripts/assert-manager-lock.sh && \
	      echo "--- strong hashing only ---" && \
	      sh scripts/assert-strong-hash.sh && \
	      echo "--- functional ---" && \
	      make clean-all && make -j$(CI_JOBS) check CXX=$(CI_CXX) CC=$(CI_CC) && \
	      echo "--- sanitizers ---" && make -j$(CI_JOBS) check SANITIZE=1 CXX=$(CI_CXX) CC=$(CI_CC) && \
	      echo "--- thread sanitizer ---" && make -j$(CI_JOBS) check THREAD=1 CXX=$(CI_CXX) CC=$(CI_CC) && \
	      echo "--- valgrind ---" && make -j$(CI_JOBS) check-valgrind CXX=$(CI_CXX) CC=$(CI_CC) && \
	      echo "--- coverage ---" && \
	      make -j$(CI_JOBS) coverage CXX=$(CI_CXX) CC=$(CI_CC) GCOV=$(CI_GCOV) >/dev/null && \
	      echo "--- cppcheck ---" && \
	      cppcheck --enable=warning,portability --error-exitcode=1 \
	        --inline-suppr --std=c++11 -Iinclude src/ tests/ && \
	      echo "--- clang-tidy ---" && \
	      make clean-all >/dev/null && \
	      bear --output compile_commands.json -- make -j$(CI_JOBS) all CXX=$(CI_CXX) CC=$(CI_CC) >/dev/null 2>&1 && \
	      sh scripts/assert-compile-db.sh compile_commands.json $(LIB_SRC) && \
	      make tidy TIDY=$(CI_TIDY) && \
	      echo "--- fuzz corpus ---" && \
	      make fuzz-corpus FUZZ_CXX=$(CI_FUZZ) >/dev/null && \
	      echo "ALL CI TIERS PASSED"'

# --- Coverage (gcov; feeds SonarCloud) ----------------------------------
# Built in its own tier so instrumented objects never mix with the ordinary
# build. Produces .gcno/.gcda beside the objects and .gcov files in
# build/coverage/.
GCOV    ?= gcov
# A floor, not a target, and a ratchet: raise it deliberately when a milestone
# lands well above it, never lower it quietly to make a build pass. Set below
# the current figure on purpose, so a new component arriving partially covered
# does not block the work that will cover it.
#
# 100% of error paths that are never *taken* proves nothing; a fault-injected
# 80% is worth more than a contrived 95%. See docs/TEST-STRATEGY.md.
COVERAGE_MIN ?= 85
COV_DIR := build/coverage
COV_BIN := $(COV_DIR)/filemover_tests
COV_FLAGS := -std=c++11 -Wall -Wextra -Werror -O0 -g --coverage
COV_OBJ := $(patsubst %.cpp,$(COV_DIR)/%.o,$(LIB_SRC) $(TEST_SRC))
# Linked in, but deliberately not instrumented: vendored third-party code must
# not appear in this project's coverage figure. gcov is pointed at $(LIB_SRC)
# below, so sqlite3.c contributes nothing to the percentage either way.
COV_SQLITE_OBJ := $(COV_DIR)/third_party/sqlite3.o

# Compiled to discrete objects rather than in one step. A single-step
# compile names the notes files after the *binary*
# (filemover_tests-json.gcno), which gcov cannot map back to a source path —
# one object per source keeps the correspondence obvious.
$(COV_DIR)/%.o: %.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(COV_FLAGS) $(DEPFLAGS) -c $< -o $@

coverage: $(COV_OBJ) $(COV_SQLITE_OBJ)
	$(CXX) $(COV_FLAGS) $(COV_OBJ) $(COV_SQLITE_OBJ) -o $(COV_BIN) $(LINK_LIBS)
	./$(COV_BIN) --use-colour no
	@# gcov must run from here, not from the report directory: it resolves
	@# each source by the relative path recorded at compile time, and writes
	@# a one-line stub if it cannot read the file. -o says where the .gcno
	@# and .gcda live; -r drops anything reached by an absolute path, which
	@# is how the system headers and Catch2 are excluded.
	@# GCOV must match the compiler that produced the .gcno files. Mixing
	@# them (gcov-11 against g++-14 output, say) fails with a version
	@# mismatch and emits nothing usable, so CI passes GCOV=gcov-14
	@# alongside CXX=g++-14.
	@# NO -b here, deliberately, and this is a TEMPORARY measure -- see the
	@# "Restore branch coverage reporting" entry in docs/ROADMAP.md.
	@#
	@# gcov's branch data for C++ is dominated by edges the compiler emits and
	@# no test can take. Measured across three files: of 685 never-taken
	@# branches, 502 (73%) sit on source lines containing no conditional at all
	@# -- `std::ostringstream os;`, `os << "store: " << what;`, `return
	@# fail(...)`. They are exception-unwind paths from std::string and
	@# ostringstream, reachable only by forcing an allocation failure.
	@#
	@# SonarCloud blends line and condition coverage into one number, so
	@# feeding it that data reported 71.3% for a tree with 91.2% line coverage,
	@# and http_parser.cpp -- which has 100% line coverage -- came out at 82.3%.
	@# The gate was then failing on an artifact rather than on a gap.
	@#
	@# The roughly 240 genuinely untaken branches are real and still worth
	@# closing. `make coverage-branches` keeps them visible; dropping the data
	@# entirely would hide them, which is the thing to avoid.
	@mkdir -p $(COV_DIR)/report
	$(GCOV) -r -o $(COV_DIR)/src $(LIB_SRC) | tail -n +1
	@mv -f *.gcov $(COV_DIR)/report/ 2>/dev/null || true
	@echo
	@sh scripts/coverage-summary.sh $(COV_DIR)/report plain $(COVERAGE_MIN)

# Branch coverage, for looking at rather than for gating on. Writes to its own
# directory so the .gcov files SonarCloud consumes stay line-only.
#
# The audit script separates the branches worth acting on from the ones the
# compiler emitted, which is the distinction that makes the raw number
# useless on its own.
.PHONY: coverage-branches
coverage-branches: $(COV_OBJ) $(COV_SQLITE_OBJ)
	$(CXX) $(COV_FLAGS) $(COV_OBJ) $(COV_SQLITE_OBJ) -o $(COV_BIN) $(LINK_LIBS)
	./$(COV_BIN) --use-colour no >/dev/null
	@mkdir -p $(COV_DIR)/branches
	@$(GCOV) -b -r -o $(COV_DIR)/src $(LIB_SRC) >/dev/null
	@mv -f *.gcov $(COV_DIR)/branches/ 2>/dev/null || true
	@for f in $(COV_DIR)/branches/*.gcov; do \
	    python3 scripts/branch-coverage-audit.py "$$f" | head -5; \
	    echo; \
	done

# --- Fuzzing (ADR-0008) --------------------------------------------------
# libFuzzer requires clang; GCC 4.8 can host neither it nor LSan. The source
# is identical across toolchains, so what is fuzzed here is what ships.
#
#   make fuzz          build the fuzzer
#   make fuzz-run      run it against the corpus (FUZZ_SECONDS, default 60)
#
# CORPUS holds committed seeds and, crucially, every input a previous run
# found interesting or crashing — a fuzzer finds a bug once, a corpus
# prevents it forever.
FUZZ_CXX      ?= clang++
FUZZ_DIR      := build/fuzz
FUZZ_SECONDS  ?= 60
FUZZ_FLAGS    := -std=c++11 -Wall -Wextra -O1 -g \
                 -fsanitize=fuzzer,address,undefined \
                 -fno-omit-frame-pointer -fno-sanitize-recover=all

# One entry per hand-rolled component that reads untrusted bytes
# (docs/HAND-ROLLED-COMPONENTS.md §2.4). Each target keeps its own corpora,
# because a corpus that mixes JSON documents with HTTP heads guides the
# fuzzer toward neither.
FUZZ_TARGETS  := json http

# What the fuzz targets link. Subtractive rather than a written-out list, so a
# new source is fuzzed by default and *excluding* one is a deliberate act --
# the same reasoning that keeps clang-tidy on $(LIB_SRC). A hand-maintained
# list is how a component quietly stops being covered.
#
# store.cpp is out because it needs the vendored SQLite object, and dragging a
# 9.5 MB amalgamation into every fuzz build costs about a minute per target for
# code no fuzz target reaches: these consume bytes with no I/O, no threads and
# no clock (ADR-0008). If a fuzz target for the store is ever written -- a
# database file is untrusted input in a way a job record is not -- this
# exclusion is the thing to revisit.
#
# mover.cpp follows store.cpp because it calls into it. This is the second time
# adding a source to LIB_SRC broke the fuzz link, which is the cost of the
# subtractive design -- and still the right trade: the alternative is a
# hand-written include list that stops covering a new parser silently, and a
# link error is a far better failure than a fuzz target quietly testing less.
FUZZ_EXCLUDE  := src/store.cpp src/mover.cpp src/manager.cpp src/server.cpp src/router.cpp src/http_service.cpp src/service.cpp src/singleton.cpp
FUZZ_LIB_SRC  := $(filter-out $(FUZZ_EXCLUDE),$(LIB_SRC))
# Derived, so adding a target to the list above cannot leave format-check
# silently covering fewer files than the build does.
FUZZ_SRC      := $(patsubst %,fuzz/fuzz_%.cpp,$(FUZZ_TARGETS))

fuzz_bin       = $(FUZZ_DIR)/fuzz_$(1)
fuzz_corpus    = fuzz/corpus-$(1)
fuzz_regress   = fuzz/corpus-regression-$(1)

.PHONY: fuzz fuzz-run fuzz-corpus
fuzz:
	@mkdir -p $(FUZZ_DIR)
	@for t in $(FUZZ_TARGETS); do \
	  echo "building fuzz target: $$t"; \
	  $(FUZZ_CXX) $(CPPFLAGS) $(FUZZ_FLAGS) \
	    fuzz/fuzz_$$t.cpp $(FUZZ_LIB_SRC) -o $(FUZZ_DIR)/fuzz_$$t || exit 1; \
	done

# libFuzzer WRITES newly-interesting inputs into the FIRST corpus directory
# it is given and treats the rest as read-only seeds. Pointing it straight at
# the committed corpus would bury the curated seeds under generated ones, so
# the working corpus is scratch space under build/.
fuzz-run: fuzz
	@for t in $(FUZZ_TARGETS); do \
	  mkdir -p $(FUZZ_DIR)/artifacts-$$t $(FUZZ_DIR)/corpus-$$t; \
	  echo "=== fuzzing $$t for $(FUZZ_SECONDS)s ==="; \
	  $(FUZZ_DIR)/fuzz_$$t $(FUZZ_DIR)/corpus-$$t \
	    fuzz/corpus-$$t fuzz/corpus-regression-$$t \
	    -max_total_time=$(FUZZ_SECONDS) -max_len=65536 \
	    -artifact_prefix=$(FUZZ_DIR)/artifacts-$$t/ \
	    -print_final_stats=1 || exit 1; \
	done

# Replays committed seeds and retained crash reproducers once, then exits.
# -runs=0 stops mutation but does NOT make the run read-only: libFuzzer still
# copies coverage-increasing inputs into the first directory, so a scratch
# directory goes first here too.
fuzz-corpus: fuzz
	@for t in $(FUZZ_TARGETS); do \
	  mkdir -p $(FUZZ_DIR)/replay-$$t; \
	  echo "=== replaying $$t corpus ==="; \
	  $(FUZZ_DIR)/fuzz_$$t -runs=0 $(FUZZ_DIR)/replay-$$t \
	    fuzz/corpus-$$t fuzz/corpus-regression-$$t || exit 1; \
	done

# --- Static analysis -----------------------------------------------------
# Requires compile_commands.json. Without it clang-tidy cannot resolve
# includes and emits a cascade of bogus findings — 34 of them, in one
# observed case — rather than reporting that its input is missing. The guard
# turns that into an actionable error.
# TIDY is overridable so CI can pin the version (see cpp-ci.yml). $(LIB_SRC)
# rather than a written-out file list: a hardcoded list in the workflow
# silently stopped covering api_codec.cpp and config.cpp when they landed,
# leaving the job green while it checked less and less.
TIDY ?= clang-tidy

# Verifies vendored files against the hashes in VENDORED.md (ADR-0004).
# A repository-wide edit once rewrote an identifier inside the vendored Catch2
# header and every other gate passed -- the compiler cannot tell, only the
# checksum can.
.PHONY: verify-vendored
verify-vendored:
	@sh scripts/verify-vendored.sh

# L3-CPP-052. The runtime test switches to tr_TR.UTF-8 and re-parses, but
# setlocale returns NULL where that locale is not generated and the test then
# downgrades itself to a warning. check-ci and the CI runner now generate it,
# and the gcc:4.8 image cannot (its wheezy apt sources are archived), so the
# coverage is uneven by environment. This gate is not: grepping the source
# cannot be skipped, so it holds wherever the runtime check does not.
.PHONY: locale-free
locale-free:
	@sh scripts/assert-locale-free.sh $(PARSER_SRC)

# L2-JOB-009. The requirement's stated method is Inspection, and inspection is
# precisely what stops happening once someone needs one quick query elsewhere.
# ADR-0010's containment only holds if something checks it.
.PHONY: sql-confined
sql-confined:
	@sh scripts/assert-sql-confined.sh

# L2-SEC-001 and L2-SEC-008, both specified as Inspection, for the same reason
# as sql-confined above: inspection is the method that stops happening.
#
# fd-relative bans the path-taking headers rather than matching call sites. A
# translation unit that cannot see <fcntl.h> cannot call open() whatever it
# names its own methods -- the call-site version of this gate flagged
# JobStore::open, and a gate with false positives gets disabled.
.PHONY: fd-relative
fd-relative:
	@sh scripts/assert-fd-relative.sh

.PHONY: no-shell
no-shell:
	@sh scripts/assert-no-shell.sh

# A test that removes write permission to force a failure asserts nothing when
# the process is root, and the GCC 4.8.5 fidelity container runs as root. C4's
# retry tests were written that way and silently exercised the success path
# there. Negative-tested by scripts/gate-selftest.sh.
.PHONY: no-permission-tests
no-permission-tests:
	@sh scripts/assert-no-permission-tests.sh

# wait_for/wait_until break ThreadSanitizer's tracking of the mutex passed to
# them, turning every access that mutex guards into a false race. C4 cost 32
# warnings and three investigation passes to that. C5 needs timeouts for
# L2-SEC-009 and is exactly where someone reaches for one.
.PHONY: no-timed-condwait
no-timed-condwait:
	@sh scripts/assert-no-timed-condwait.sh

# Every acquisition of the manager mutex must go through ManagerLock, which
# maintains the thread-local depth count that store_for_command asserts on. A
# raw unique_lock or lock_guard silently disables the assertion for that path.
.PHONY: manager-lock
manager-lock:
	@sh scripts/assert-manager-lock.sh

# L2-SEC-015. Preventive: integrity verification is deferred to v1.1, so this
# finds nothing today. It exists so the constraint is enforced the moment the
# feature arrives rather than remembered afterwards -- v1.1 being exactly when
# someone reaches for the first hash function they recognise.
.PHONY: strong-hash
strong-hash:
	@sh scripts/assert-strong-hash.sh

# The minimum clang-tidy major version this gate is meaningful at. CI runs
# CI_TIDY (clang-tidy-20); a developer running an older one gets a PASS that
# means "my clang-tidy does not know about these checks", which is the most
# expensive kind of green.
#
# This is not hypothetical. C4 landed on a machine with clang-tidy 14 and was
# clean locally while CI failed with twenty misc-const-correctness errors --
# that check arrived in clang-tidy 17, so the local run could not see what the
# gate enforces. The build must not report success for a check it did not run.
TIDY_MIN_MAJOR ?= 17

tidy:
	@sh scripts/assert-compile-db.sh compile_commands.json $(LIB_SRC)
	@sh scripts/assert-tidy-version.sh $(TIDY) $(TIDY_MIN_MAJOR)
	$(TIDY) -p . --quiet --warnings-as-errors='*' $(LIB_SRC)

# Runs the clang-tidy gate the way CI runs it, in the CI image, with CI's
# binary. The same reasoning as check-gcc48 above: one target, one image, both
# callers.
#
# This exists because the local and CI binaries are not the same and cannot
# easily be made the same. Ubuntu 22.04 ships clang-tidy up to 15; CI uses 20.
# `make tidy` on a 22.04 host therefore either lies (before TIDY_MIN_MAJOR) or
# refuses (after it), and neither tells a developer whether their change passes.
# This does.
#
# It regenerates compile_commands.json inside the image, because clang-tidy
# aborts outright on a database recorded by a different compiler -- which is
# how it fails if you mount a locally-built tree and run only the tidy step.
#
# Wipes the build tree first, as check-gcc48 does, so the objects and the
# database describe the same compiler.
.PHONY: tidy-ci
tidy-ci:
	$(CI_ENGINE) run --rm -v $(CURDIR):/cpp -w /cpp $(CI_IMAGE) sh -c '\
	  make clean-all >/dev/null && \
	  bear -- make -j$(CI_JOBS) all CXX=$(CI_CXX) CC=$(CI_CC) >/dev/null && \
	  make tidy TIDY=$(CI_TIDY) CXX=$(CI_CXX) CC=$(CI_CC)'

# ADVISORY, not a gate, and it does not currently pass -- see the NOTE in
# .github/workflows/cpp-ci.yml. The sources use column alignment clang-format
# rewrites, so this reports most of the tree as violating and always has. That
# is a deliberate open decision (bulk-reformat tested code, or drop the tool),
# not a regression to chase.
#
# Recorded here because the wall of output reads exactly like a real failure:
# it was mistaken for a clang-format version gap once, and the "fix" attempted
# was a version guard asserting the tree is formatted by CI's binary -- which
# it is not, by choice. Do not reformat to make this quiet without agreeing to
# the reformat first.
FORMAT ?= clang-format

.PHONY: format-check
format-check:
	$(FORMAT) --dry-run --Werror $(LIB_SRC) $(TEST_SRC) \
	    $(FUZZ_SRC) include/filemover/*.hpp

# Generated header dependencies (see DEPFLAGS above). Leading '-' because none
# of these exist on a first build, and their absence is not an error. Kept at
# the foot of the file so the included rules cannot displace the default goal.
-include $(LIB_OBJ:.o=.d)
-include $(TEST_OBJ:.o=.d)
-include $(COV_OBJ:.o=.d)

# NOTE: the two -Wno-maybe-uninitialized exemptions that previously covered
# api_codec.o and test_api_codec.o were removed with picojson (ADR-0006).
# -Werror is now unqualified across every translation unit, which L2-ARC-007
# requires. Do not reintroduce a per-object warning exemption without an ADR.
