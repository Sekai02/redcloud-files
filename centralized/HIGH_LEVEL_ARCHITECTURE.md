+--------------------------------------------------------------+
|                      External Machines                       |
|                                                              |
|   +---------+    +---------+    +---------+                  |
|   |  CLI 1  |    |  CLI 2  |    |  CLI N  |   ...            |
|   +----+----+    +----+----+    +----+----+                  |
|        \              |              /                       |
+---------\-------------|-------------/------------------------+
          \             |            /
           \            |           /
            v           v          v
+--------------------------------------------------------------+
|        Docker Swarm Host(s) + Overlay Network (dfs-net)      |
|                                                                  |
|   +-------------------+         +----------------------------+   |
|   |   Controller      |  RPC    |        Chunkserver         |   |
|   |   (container)     +-------->+        (container)         |   |
|   | - metadata        |  read   | - chunk files on /data     |   |
|   | - tag queries     |  write  | - checksum verify          |   |
|   | - operations      |         | - local chunk index        |   |
|   +-------------------+         +----------------------------+   |
+--------------------------------------------------------------+

CLIs connect to the Controller via host IP + exposed port (e.g. hostA:9000).
Controller and Chunkserver talk over the overlay network by container name.
