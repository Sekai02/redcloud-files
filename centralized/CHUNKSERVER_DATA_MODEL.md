Chunkserver (local storage + index)
===================================

+----------------------------------------------------------+
|                      Chunkserver                         |
+---------------------------+------------------------------+
|  chunkIndex: Map<chunk_id, ChunkRecord>                  |
|  data dir  : /data/chunks/                               |
+---------------------------+------------------------------+

ChunkRecord
-----------

  +----------------------------------------------+
  |                 ChunkRecord                  |
  +---------------------+------------------------+
  | chunk_id  : UUID                             |
  | file_id   : UUID                             |
  | index     : Int                              |
  | length    : Int                              |
  | checksum  : Bytes                            |
  | path      : String ("/data/chunks/<id>.chk") |
  +---------------------+------------------------+

On-disk file layout (per chunk file)
------------------------------------

  Path: /data/chunks/<chunk_id>.chk

  +---------------------------+
  |        Header             |
  |---------------------------|
  | file_id    (fixed size)   |
  | index      (int)          |
  | length     (int)          |
  | checksum   (bytes)        |
  +---------------------------+
  |           Data            |
  |  (length bytes of file)   |
  +---------------------------+
