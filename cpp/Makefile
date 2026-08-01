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
CXXFLAGS ?= -std=c++11 -Wall -Wextra -Werror -O1 -g \
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

.PHONY: all check clean clean-all check-valgrind toolchain

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

# NOTE: the two -Wno-maybe-uninitialized exemptions that previously covered
# api_codec.o and test_api_codec.o were removed with picojson (ADR-0006).
# -Werror is now unqualified across every translation unit, which L2-ARC-007
# requires. Do not reintroduce a per-object warning exemption without an ADR.
