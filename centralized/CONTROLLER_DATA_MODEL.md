Controller (in-memory + persisted metadata)
===========================================

+----------------------------------------------------------+
|                      Controller                          |
+---------------------------+------------------------------+
|  files: Map<file_id, FileMeta>                           |
|  tagIndex: Map<tag, Set<file_id>>                        |
+---------------------------+------------------------------+

FileMeta
--------

  +----------------------------------------------+
  |                 FileMeta                     |
  +---------------------+------------------------+
  | file_id   : UUID                              |
  | name      : String (human filename)           |
  | tags      : Set<String>                       |
  | deleted   : Bool                              |
  | chunks    : List<ChunkDescriptor>             |
  +---------------------+------------------------+

ChunkDescriptor
---------------

  +----------------------------------------------+
  |              ChunkDescriptor                 |
  +---------------------+------------------------+
  | chunk_id  : UUID                             |
  | file_id   : UUID (backref to file)           |
  | index     : Int   (0,1,2,...)               |
  | length    : Int   (<= 64 MiB)               |
  | checksum  : Bytes (SHA-256, 32 bytes)       |
  +---------------------+------------------------+

Tag Index
---------

  tagIndex : Map<tag, Set<file_id>>

  Example:

    tagIndex = {
      "projectA" -> { file1, file3, file7 },
      "report"   -> { file2, file3 },
      "image"    -> { file4 }
    }
