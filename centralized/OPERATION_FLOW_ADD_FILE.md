ADD FLOW (one file)
===================

CLI                         Controller                     Chunkserver
---                         ----------                     -----------

1) User runs:
     add file.txt projectA report

2) CLI opens TCP connection to Controller (hostA:9000)

3) CLI -> Controller:
     "ADD"
     - file_name = "file.txt"
     - tags = ["projectA", "report"]
     - file bytes stream

                            4) Controller:
                               - allocate file_id = F123
                               - create temporary FileMeta(F123, "file.txt", tags, deleted=false)
                               - start reading file stream
                               - split into 64 MiB chunks

                               (Note: FileMeta is built locally, not yet added to files map)

                            For each chunk:

                            5) Controller:
                               - compute checksum
                               - assign chunk_id = Ck_i
                               - index = i
                               - length = chunk_size or last_chunk_size
                               - add ChunkDescriptor(Ck_i, F123, i, length, checksum)
                               - append to FileMeta.chunks

                            6) Controller -> Chunkserver:
                               writeChunk(
                                 chunk_id,
                                 file_id,
                                 index,
                                 length,
                                 checksum,
                                 data
                               )

                                                          7) Chunkserver:
                                                             - verify checksum(data)
                                                             - write /data/chunks/<chunk_id>.chk
                                                               with header + data
                                                             - update chunkIndex[chunk_id]
                                                             - reply "OK" or "ERROR"

                            8) Controller:
                               - if all chunks OK:
                                   files[F123] = FileMeta(...)  # commit to files map
                                   for each tag in ["projectA","report"]:
                                     tagIndex[tag].add(F123)
                               - if any chunk fails:
                                   discard temporary FileMeta
                                   (optionally request Chunkserver to delete partial chunks)

9) Controller -> CLI:
     "ADD result: success" (or detailed error)
