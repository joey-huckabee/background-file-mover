# Streaming integrity plan

The agreed filesystem copy path computes the source digest during copying,
then rereads destination staging to verify it before publication. Use incremental
SHA-256 as the initial design; the implementation crate/version still requires
qualification. There is no separate source prehash pass in the normal workflow.

The proposed [transfer protocol](TRANSFER-PROTOCOL.md) applies this agreement to
source custody, publication, recording-set commitment and cleanup. Its
[REST draft](REST-API-DRAFT.md) separates acceptance from source-path release.

## Normal filesystem path

1. Record intent, source identity/declared size, integrity algorithm and operation
   ownership. Claim the source under the producer's completed-file handoff contract.
   A rename does not prevent an existing writer from modifying the file.
2. Create exclusively owned destination staging. Read the source once through a
   bounded reusable buffer, update the source hash and write the same byte stream
   completely. Handle partial writes and failures explicitly.
3. After successful EOF/size checks, synchronize staging data and required directory
   entries. Persist the completed source digest, byte count and staging/attempt
   identity. A partial copy or failed sync is not a verified transfer.
4. Reread staging, independently calculate its digest and byte count, and compare
   them with the durable copy evidence. Reject mismatches and retain the source.
5. Publish verified staging without clobbering unrelated data, commit the recording
   set/manifest, and only then authorize cleanup of the claimed source.

The digest describes the bytes read and transferred, rather than a separately
hashed source snapshot. Closed writers/no subsequent source modification remain
required. Identity/size/time checks supplement that contract; they do not prove
immutability. A producer-supplied expected digest may be checked during copying
without imposing another source read.

## I/O accounting

For an N-byte file on the normal successful copied-file path:

| Operation | Logical data I/O |
|---|---|
| Source read, with incremental hashing | N |
| Destination write | N |
| Destination reread, with verification hashing | N |
| Total | 3N |

A 100 GB file therefore accounts for approximately 300 GB of logical data I/O,
while only 100 GB of payload is copied to the destination. Hash calculation adds
CPU work without an additional source pass. Physical disk I/O and network traffic
depend on endpoint placement, caching and the filesystem; they are not necessarily
300 GB. Metadata, synchronization, retries and recovery add work beyond this model.

Reread verification checks content returned by the storage stack. Cache hits and
successful sync calls do not independently prove survival of every server/storage
power-loss scenario; qualify and document those assumptions separately.

## Recovery requirements

The completed source digest becomes available after copying, not before it begins.
Record that distinction in the state/evidence model instead of requiring a
SourceHashed phase before Copying.

Retain the claimed source until verified recording-set commitment. If copying
is interrupted without durable complete-copy evidence, restart from the retained
source into a new owned staging attempt; retire old staging only with proven
ownership. Do not infer completion from plausible length or a partial hash.
If complete-copy evidence exists, reconcile staging/final identity and content
before advancing. Uncertain effects require reconciliation, not blind recopy or
deletion. Resume checkpoints remain a separate future design.

## Future S3 adapter

S3 can validate checksums while receiving uploads, potentially avoiding a client
download for destination verification. This is a backend-specific protocol to
qualify, not a change to the agreed filesystem reread policy.

AWS currently defaults to CRC64NVME when adding a checksum. Multipart SHA-256
uses a composite checksum of parts, rather than the ordinary whole-file SHA-256;
multipart full-object checksums support CRC algorithms. Specify/check the algorithm
and checksum type instead of comparing unlike digests.
[AWS upload checksum documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html).

An ETag is not a SHA-256 digest. Use explicit checksum fields and independently
computed expected values; simply receiving a server checksum or storing a client
hash as user metadata does not validate equivalence to source bytes.
[AWS PutObject reference](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html).

For an S3 design, evaluate streamed per-part SHA-256 validation/composite evidence
or a matching full-object CRC policy. Bind receipts to object/operation identity,
size, algorithm, checksum type, part ordering and version where applicable. Retain
a streamed whole-file SHA-256 in durable records/manifests when required, without
mislabeling it as a server-validated whole-file SHA-256. Qualify provider-specific
behavior for S3-compatible services. Avoiding extra client reads does not make
hash CPU work, API requests or storage service charges disappear.
