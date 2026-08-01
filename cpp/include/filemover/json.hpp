#ifndef FILEMOVER_JSON_HPP
#define FILEMOVER_JSON_HPP

// Project-owned strict-subset JSON parser (ADR-0006, ADR-0009).
//
// This is the first code to touch untrusted network bytes, so the grammar is
// deliberately smaller than RFC 8259: everything the API does not need is
// rejected rather than parsed. A parser that accepts less has less to get
// wrong.
//
// Traces: L2-JSON-001..005, L1-ROB-001, L1-ROB-002
//
// Accepted (ADR-0009):
//   * top-level value MUST be an object
//   * member values: string, integer (int64), boolean, object, array
//   * nesting bounded by Limits::max_depth, checked BEFORE descending
//
// Rejected, non-exhaustively: floating point and exponents, null, duplicate
// member names, trailing bytes after the top-level value, trailing commas,
// comments, unquoted or single-quoted strings, a leading BOM, embedded NUL,
// unescaped control characters, lone surrogates, invalid/overlong UTF-8,
// leading zeros, leading '+', bare ".5"/"5.", NaN/Infinity/hex.

#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace filemover {
namespace json {

class Value;

// Object members are stored in document order rather than a map: the set is
// tiny, order aids diagnostics, and duplicate detection is an explicit scan
// (ADR-0009 rejects duplicates rather than picking a winner, because
// last-wins/first-wins disagreement between parsers is a classic
// auth-bypass differential).
struct Member;

class Value {
public:
    enum class Type { Bool, Int, String, Array, Object };

    Value();  // defaults to Bool(false); the parser always overwrites

    Type type() const { return type_; }

    bool is_bool() const { return type_ == Type::Bool; }
    bool is_int() const { return type_ == Type::Int; }
    bool is_string() const { return type_ == Type::String; }
    bool is_array() const { return type_ == Type::Array; }
    bool is_object() const { return type_ == Type::Object; }

    // Accessors are unchecked on type; callers test with is_*() first. The
    // codec is the only caller and always does.
    bool as_bool() const { return bool_; }
    std::int64_t as_int() const { return int_; }
    const std::string& as_string() const { return string_; }
    const std::vector<Value>& as_array() const { return array_; }
    const std::vector<Member>& as_object() const { return members_; }

    // Returns null when absent. The returned pointer is owned by this Value
    // and is invalidated by any mutation.
    const Value* find(const std::string& key) const;

    void set_bool(bool v);
    void set_int(std::int64_t v);
    void set_string(const std::string& v);
    void set_array();
    void set_object();

    // Valid only after set_array()/set_object().
    std::vector<Value>& mutable_array() { return array_; }
    std::vector<Member>& mutable_object() { return members_; }

private:
    Type type_;
    bool bool_;
    std::int64_t int_;
    std::string string_;
    // Recursive members. Instantiation of these containers happens where
    // Value is complete (its constructors/destructor), which is what
    // libstdc++ requires and what C++17 later blessed outright.
    std::vector<Value> array_;
    std::vector<Member> members_;
};

struct Member {
    std::string key;
    Value value;
};

// Resource bounds (ADR-0009). Every limit exists to stop a specific
// exhaustion vector, not for tidiness:
//   max_depth        stack exhaustion via [[[[...]]]]
//   max_input_bytes  overall memory; shared with the HTTP 413 cap (L1-API-004)
//   max_string_bytes single-token amplification
//   max_members      many-small-tokens amplification within one object
//   max_elements     the same, within one array
struct Limits {
    std::size_t max_depth;
    std::size_t max_input_bytes;
    std::size_t max_string_bytes;
    std::size_t max_members;
    std::size_t max_elements;

    Limits();
};

// Parses `input` as a complete JSON document under `limits`.
//
// Returns true and fills `out` on success. Returns false on any violation,
// fills `error` with a non-empty human-readable message, and leaves `out`
// unspecified. Never throws, never aborts, and never terminates the process
// regardless of input size, nesting, or content (L1-ROB-001, L1-ROB-002).
bool parse(const std::string& input,
           Value& out,
           std::string& error,
           const Limits& limits);

bool parse(const std::string& input, Value& out, std::string& error);

// Escapes `in` as a JSON string body (without surrounding quotes) such that
// parsing the result reproduces `in` exactly.
std::string escape(const std::string& in);

}  // namespace json
}  // namespace filemover

#endif  // FILEMOVER_JSON_HPP
