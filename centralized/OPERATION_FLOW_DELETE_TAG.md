DELETE-TAGS FLOW
================

CLI                         Controller
---                         ----------

1) User runs:
     delete-tags projectA report reviewed

   (meaning: for all files matching [projectA, report],
    remove tag "reviewed")

2) CLI -> Controller:
     "DELETE-TAGS"
     - tag_query = ["projectA", "report"]
     - tags_to_remove = ["reviewed"]

                            3) Controller:
                               - resolve tag_query via tagIndex:
                                   S1 = tagIndex["projectA"]
                                   S2 = tagIndex["report"]
                                   S  = S1 ∩ S2
                               - for each file_id in S:
                                   fm = files[file_id]
                                   if fm.deleted == false:
                                     for each t in tags_to_remove:
                                       fm.tags.remove(t)
                                       tagIndex[t].remove(file_id)

4) Controller -> CLI:
     "DELETE-TAGS result: success"
