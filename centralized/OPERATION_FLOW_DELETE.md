DELETE FLOW
===========

CLI                         Controller                    Chunkserver (optional GC)
---                         ----------                    -------------------------

1) User runs:
     delete projectA report

2) CLI -> Controller:
     "DELETE"
     - tag_query = ["projectA", "report"]

                            3) Controller:
                               - resolve tag_query via tagIndex:
                                   S1 = tagIndex["projectA"]
                                   S2 = tagIndex["report"]
                                   S  = S1 ∩ S2
                               - for each file_id in S:
                                   files[file_id].deleted = true
                                   for each tag in files[file_id].tags:
                                      tagIndex[tag].remove(file_id)

4) Controller -> CLI:
     "DELETE result: success"

                            (later, background job:)

                            5) Controller:
                               - periodically scan files[]
                               - for each file with deleted=true:
                                   decide whether to GC now

                            6) Controller -> Chunkserver:
                               for each chunk in FileMeta.chunks:
                                 deleteChunk(chunk_id)

                                                          7) Chunkserver:
                                                             - remove /data/chunks/<chunk_id>.chk
                                                             - remove chunkIndex[chunk_id]
