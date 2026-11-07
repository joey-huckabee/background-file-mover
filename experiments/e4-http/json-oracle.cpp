// Build-host-only oracle; never linked into the Rust service probes.
#include "filemover/json.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        std::ifstream file(argv[i], std::ios::binary);
        if (!file) return 2;
        const std::string input((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        filemover::json::Value value;
        std::string error;
        const bool accepted = filemover::json::parse(input, value, error);
        const std::string path(argv[i]);
        std::cout << path.substr(path.find_last_of('/') + 1) << '\t' << (accepted ? "ACCEPT" : "REJECT") << '\n';
    }
}
