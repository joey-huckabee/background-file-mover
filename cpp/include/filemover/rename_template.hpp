#ifndef FILEMOVER_RENAME_TEMPLATE_HPP
#define FILEMOVER_RENAME_TEMPLATE_HPP

// Rename template expansion — a pure function of its inputs.
//
// This is the template engine ONLY. The filesystem operation that consumes it
// is deliberately absent: it belongs to the fd-relative layer specified in
// docs/CYBERSECURITY.md, not here. See section 10 of that document for why the
// inherited path-based rename operation was not adopted alongside this.
//
// Traces: L2-REN-001, L1-SYS-013
//
// Template fields (L3-CPP-042):
//   {name}  original basename                       a.tar.gz
//   {stem}  basename up to the last '.'             a.tar
//   {ext}   after the last '.', empty if none       gz
//           (a leading dot is NOT an extension separator: ".bashrc" has
//            stem ".bashrc" and empty ext)
//   {ts}    at_ms as UTC  YYYYMMDD"T"HHMMSS"."mmm   20260801T093015.250
//   {seq}   sequence, zero-padded to 6 digits       000042
//
// NOTE on {seq}: the sequence is supplied by the caller and this function is
// pure, so a monotonic counter has to live in durable state. Nothing
// specifies it yet — see the open question in docs/ROADMAP.md. A counter that
// resets on restart makes {seq} templates collide on every boot.

#include <cstdint>
#include <string>

namespace filemover {

// Inputs a template may reference that are not derivable from the filename.
// Both are caller-supplied: the core reads no clock (L2-CORE-004), and this
// function reads no state.
struct RenameContext {
    std::int64_t at_ms;
    std::uint64_t sequence;

    RenameContext() : at_ms(0), sequence(0) {}
};

// Expand `templ` against the basename of the file being renamed.
//
// L3-CPP-042: SHALL support exactly {name}, {stem}, {ext}, {ts}, {seq}.
// L3-CPP-043: an unknown field, an unclosed '{', or a stray '}' SHALL be an
//             error naming the offending construct.
// L3-CPP-044: the expansion result SHALL be rejected if empty, ".", "..", or
//             containing '/' or NUL — a template can never make the rename
//             escape its directory.
// L3-CPP-045: SHALL perform no I/O and SHALL read no clock.
//
// On failure: returns false, `error` is non-empty, `out` is unmodified.
bool expand_rename_template(const std::string& templ,
                            const std::string& source_name,
                            const RenameContext& context,
                            std::string& out,
                            std::string& error);

}  // namespace filemover

#endif  // FILEMOVER_RENAME_TEMPLATE_HPP
