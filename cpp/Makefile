# Background File Mover — C++ build (ADR-0005)
# Target toolchain: GCC 4.8.5 on SLES 12 SP5. Keep everything C++11-clean.

CXX      ?= g++
CXXFLAGS ?= -std=c++11 -Wall -Wextra -Werror -O2 -g
CPPFLAGS += -Iinclude -isystem third_party

BUILD_DIR := build

LIB_SRC  := src/job.cpp
LIB_OBJ  := $(patsubst src/%.cpp,$(BUILD_DIR)/src/%.o,$(LIB_SRC))

TEST_SRC := tests/test_main.cpp tests/test_job.cpp
TEST_OBJ := $(patsubst tests/%.cpp,$(BUILD_DIR)/tests/%.o,$(TEST_SRC))

TEST_BIN := $(BUILD_DIR)/filemover_tests

.PHONY: all check clean

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

clean:
	rm -rf $(BUILD_DIR)

# --- Memory-safety instrumentation (modern toolchains; CI jobs) ---------
# Usage: make check SANITIZE=1     (AddressSanitizer + UBSan + LeakSanitizer)
#        make check-valgrind       (Valgrind memcheck, error on any finding)
# GCC 4.8 has only partial ASan and no LSan, so sanitizer jobs run on the
# modern compiler; the code under test is identical because the source is
# strictly C++11-conformant and compiled from one body (ADR-0001).
SANITIZE ?= 0
ifeq ($(SANITIZE),1)
CXXFLAGS := -std=c++11 -Wall -Wextra -Werror -O1 -g \
            -fsanitize=address,undefined -fno-omit-frame-pointer \
            -fno-sanitize-recover=all
endif

.PHONY: check-valgrind
check-valgrind: $(TEST_BIN)
	valgrind --tool=memcheck --leak-check=full --show-leak-kinds=all \
	  --errors-for-leak-kinds=all --error-exitcode=1 \
	  $(TEST_BIN) --use-colour no

# NOTE: the two -Wno-maybe-uninitialized exemptions that previously covered
# api_codec.o and test_api_codec.o were removed with picojson (ADR-0006).
# -Werror is now unqualified across every translation unit. Do not
# reintroduce a per-object warning exemption without an ADR.
