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
TIER := asan
else
CXXFLAGS ?= -std=c++11 -Wall -Wextra -Werror -O2 -g
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

LIB_SRC  := src/job.cpp src/json.cpp
LIB_OBJ  := $(patsubst src/%.cpp,$(BUILD_DIR)/src/%.o,$(LIB_SRC))

TEST_SRC := tests/test_main.cpp tests/test_job.cpp tests/test_json.cpp
TEST_OBJ := $(patsubst tests/%.cpp,$(BUILD_DIR)/tests/%.o,$(TEST_SRC))

TEST_BIN := $(BUILD_DIR)/filemover_tests

.PHONY: all check clean clean-all check-valgrind toolchain \
        fuzz fuzz-run fuzz-corpus coverage tidy format-check

all: $(TEST_BIN)

$(BUILD_DIR)/src/%.o: src/%.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(BUILD_DIR)/tests/%.o: tests/%.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c $< -o $@

$(TEST_BIN): $(LIB_OBJ) $(TEST_OBJ)
	$(CXX) $(CXXFLAGS) $^ -o $@

check: $(TEST_BIN)
	$(TEST_BIN) --use-colour no

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

check-valgrind: $(TEST_BIN)
	valgrind --tool=memcheck --leak-check=full --show-leak-kinds=all \
	  --errors-for-leak-kinds=all --error-exitcode=1 \
	  $(TEST_BIN) --use-colour no

# --- Coverage (gcov; feeds SonarCloud) ----------------------------------
# Built in its own tier so instrumented objects never mix with the ordinary
# build. Produces .gcno/.gcda beside the objects and .gcov files in
# build/coverage/.
COV_DIR := build/coverage
COV_BIN := $(COV_DIR)/filemover_tests
COV_FLAGS := -std=c++11 -Wall -Wextra -Werror -O0 -g --coverage
COV_OBJ := $(patsubst %.cpp,$(COV_DIR)/%.o,$(LIB_SRC) $(TEST_SRC))

# Compiled to discrete objects rather than in one step. A single-step
# compile names the notes files after the *binary*
# (filemover_tests-json.gcno), which gcov cannot map back to a source path —
# one object per source keeps the correspondence obvious.
$(COV_DIR)/%.o: %.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CPPFLAGS) $(COV_FLAGS) -c $< -o $@

coverage: $(COV_OBJ)
	$(CXX) $(COV_FLAGS) $(COV_OBJ) -o $(COV_BIN)
	./$(COV_BIN) --use-colour no
	@# gcov must run from here, not from the report directory: it resolves
	@# each source by the relative path recorded at compile time, and writes
	@# a one-line stub if it cannot read the file. -o says where the .gcno
	@# and .gcda live; -r drops anything reached by an absolute path, which
	@# is how the system headers and Catch2 are excluded.
	@mkdir -p $(COV_DIR)/report
	gcov -b -r -o $(COV_DIR)/src $(LIB_SRC) | tail -n +1
	@mv -f *.gcov $(COV_DIR)/report/ 2>/dev/null || true
	@echo
	@sh scripts/coverage-summary.sh $(COV_DIR)/report

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
FUZZ_BIN      := $(FUZZ_DIR)/fuzz_json
FUZZ_SECONDS  ?= 60
CORPUS        := fuzz/corpus
REGRESSION    := fuzz/corpus-regression
FUZZ_FLAGS    := -std=c++11 -Wall -Wextra -O1 -g \
                 -fsanitize=fuzzer,address,undefined \
                 -fno-omit-frame-pointer -fno-sanitize-recover=all

fuzz:
	@mkdir -p $(FUZZ_DIR)
	$(FUZZ_CXX) $(CPPFLAGS) $(FUZZ_FLAGS) \
	    fuzz/fuzz_json.cpp $(LIB_SRC) -o $(FUZZ_BIN)

# libFuzzer WRITES newly-interesting inputs into the FIRST corpus directory
# it is given and treats the rest as read-only seeds. Pointing it straight at
# the committed corpus would bury 38 curated seeds under hundreds of generated
# ones, so the working corpus is a scratch directory under build/.
#
# Promote a generated input to the committed corpus only deliberately, when it
# covers a branch the seeds miss.
fuzz-run: fuzz
	@mkdir -p $(FUZZ_DIR)/artifacts $(FUZZ_DIR)/corpus
	$(FUZZ_BIN) $(FUZZ_DIR)/corpus $(CORPUS) $(REGRESSION) \
	    -max_total_time=$(FUZZ_SECONDS) \
	    -max_len=65536 \
	    -artifact_prefix=$(FUZZ_DIR)/artifacts/ \
	    -print_final_stats=1

# Replays the committed seeds and every retained crash reproducer once, then
# exits. This is the regression gate — cheap enough for every PR, unlike a
# timed session.
#
# -runs=0 stops mutation but does NOT make the run read-only: libFuzzer still
# copies coverage-increasing inputs between corpus directories, into the first
# one. A scratch directory therefore goes first here too, or the gate quietly
# rewrites the corpus it is supposed to be checking.
fuzz-corpus: fuzz
	@mkdir -p $(FUZZ_DIR)/replay
	$(FUZZ_BIN) -runs=0 $(FUZZ_DIR)/replay $(CORPUS) $(REGRESSION)

# --- Static analysis -----------------------------------------------------
# Both require compile_commands.json: bear -- make all   (see CONTRIBUTING.md)
tidy:
	clang-tidy -p . --quiet $(LIB_SRC)

format-check:
	clang-format --dry-run --Werror $(LIB_SRC) $(TEST_SRC) \
	    fuzz/fuzz_json.cpp include/filemover/*.hpp

# NOTE: the two -Wno-maybe-uninitialized exemptions that previously covered
# api_codec.o and test_api_codec.o were removed with picojson (ADR-0006).
# -Werror is now unqualified across every translation unit, which L2-ARC-007
# requires. Do not reintroduce a per-object warning exemption without an ADR.
