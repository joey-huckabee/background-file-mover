#!/bin/sh
# Regenerates the libFuzzer seed corpus for the HTTP request parser
# (ADR-0008, docs/HAND-ROLLED-COMPONENTS.md §2.4).
#
# Seeds reach distinct branches quickly; they are not required to be valid.
# libFuzzer mutates from these, so a rejection path is as useful a starting
# point as an accepted request. Crash reproducers belong in
# ../corpus-regression-http/, committed so a finding cannot come back.
#
# Usage:  sh fuzz/make-seeds-http.sh
set -eu

DIR="$(dirname "$0")/corpus-http"
mkdir -p "$DIR"

# printf %b interprets the \r\n escapes; CRLF framing is the whole point.
seed() {
    printf '%b' "$2" > "$DIR/$1"
}

# --- accepted ------------------------------------------------------------
seed get-root            'GET / HTTP/1.1\r\nHost: localhost\r\n\r\n'
seed get-jobs            'GET /api/jobs HTTP/1.1\r\nHost: h\r\n\r\n'
seed get-job-by-id       'GET /api/jobs/job-000001 HTTP/1.1\r\nHost: h\r\n\r\n'
seed get-status          'GET /api/status HTTP/1.1\r\nHost: h\r\n\r\n'
seed post-with-body      'POST /api/jobs HTTP/1.1\r\nHost: h\r\nContent-Length: 33\r\n\r\n{"source":"/a/b","dest":"/c/d"}'
seed http10              'GET / HTTP/1.0\r\nHost: h\r\n\r\n'
seed no-headers          'GET / HTTP/1.1\r\n\r\n'
seed zero-length-body    'POST /api/jobs HTTP/1.1\r\nContent-Length: 0\r\n\r\n'
seed ows-heavy           'GET / HTTP/1.1\r\nHost:    spaced   \r\n\r\n'
seed mixed-case-headers  'GET / HTTP/1.1\r\nHOST: a\r\nAccept-Encoding: gzip\r\n\r\n'

# --- rejected, one per branch --------------------------------------------
seed r-lowercase-method  'get / HTTP/1.1\r\n\r\n'
seed r-two-field-line    'GET /\r\n\r\n'
seed r-four-field-line   'GET / HTTP/1.1 extra\r\n\r\n'
seed r-relative-target   'GET api/jobs HTTP/1.1\r\n\r\n'
seed r-http2             'GET / HTTP/2.0\r\n\r\n'
seed r-long-method       'VERYLONGMETHODNAME / HTTP/1.1\r\n\r\n'
seed r-obs-fold          'GET / HTTP/1.1\r\nHost: a\r\n folded\r\n\r\n'
seed r-obs-fold-tab      'GET / HTTP/1.1\r\nHost: a\r\n\tfolded\r\n\r\n'
seed r-dup-header        'GET / HTTP/1.1\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n'
seed r-dup-header-case   'GET / HTTP/1.1\r\nHost: a\r\nHOST: b\r\n\r\n'
seed r-no-colon          'GET / HTTP/1.1\r\nNoColonHere\r\n\r\n'
seed r-empty-name        'GET / HTTP/1.1\r\n: value\r\n\r\n'
seed r-space-in-name     'GET / HTTP/1.1\r\nBad Name: v\r\n\r\n'
seed r-paren-in-name     'GET / HTTP/1.1\r\nBad(Name): v\r\n\r\n'
seed r-te-chunked        'POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n'
seed r-te-and-cl         'POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\nContent-Length: 5\r\n\r\n'
seed r-cl-plus           'POST / HTTP/1.1\r\nContent-Length: +5\r\n\r\n'
seed r-cl-negative       'POST / HTTP/1.1\r\nContent-Length: -5\r\n\r\n'
seed r-cl-hex            'POST / HTTP/1.1\r\nContent-Length: 0x10\r\n\r\n'
seed r-cl-huge           'POST / HTTP/1.1\r\nContent-Length: 99999999999999999999\r\n\r\n'
seed r-cl-comma          'POST / HTTP/1.1\r\nContent-Length: 5,5\r\n\r\n'
seed r-bare-lf           'GET / HTTP/1.1\nHost: a\n\n'
seed r-empty-line-first  '\r\n\r\n'
seed r-just-crlf         '\r\n'
seed r-garbage           'not an http request at all'

# Control characters need %b too.
printf '%b' 'GET /a\001b HTTP/1.1\r\n\r\n'          > "$DIR/r-ctl-in-target"
printf '%b' 'GET / HTTP/1.1\r\nHost: a\001b\r\n\r\n' > "$DIR/r-ctl-in-value"

echo "seeded $(ls -1 "$DIR" | wc -l) files in $DIR"
