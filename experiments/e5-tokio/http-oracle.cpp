// Build-host-only oracle for head verdict, consumed length and CL policy.
#include "filemover/http_parser.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        std::ifstream file(argv[i], std::ios::binary);
        if (!file) return 2;
        const std::string input((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        filemover::http::Request request;
        std::string error;
        std::size_t consumed = 0;
        const filemover::http::HeadParse result = filemover::http::parse_request_head(input, 8192, request, consumed, error);
        const std::string path(argv[i]);
        std::cout << path.substr(path.find_last_of('/') + 1) << '\t';
        switch (result) {
            case filemover::http::HeadParse::NeedMore: std::cout << "NEED_MORE"; break;
            case filemover::http::HeadParse::Bad: std::cout << "BAD"; break;
            case filemover::http::HeadParse::TooLarge: std::cout << "TOO_LARGE"; break;
            case filemover::http::HeadParse::Ok: {
                std::uint64_t length = 0;
                int status = 0;
                if (filemover::http::content_length_for(request, 65536, length, status, error))
                    std::cout << "OK:" << consumed << ':' << length;
                else std::cout << "CL:" << status;
                break;
            }
        }
        std::cout << '\n';
    }
}
