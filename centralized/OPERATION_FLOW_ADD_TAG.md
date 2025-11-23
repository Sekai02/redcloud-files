ADD-TAGS FLOW
=============

CLI                         Controller
---                         ----------

1) User runs:
     add-tags projectA report reviewed final

   (meaning: for all files matching tags [projectA, report],
    add new tags [reviewed, final])

2) CLI -> Controller:
     "ADD-TAGS"
     - tag_query = ["projectA", "report"]
     - new_tags  = ["reviewed", "final"]

                            3) Controller:
                               - resolve tag_query via tagIndex:
                                   S1 = tagIndex["projectA"]
                                   S2 = tagIndex["report"]
                                   S  = S1 ∩ S2
                               - for each file_id in S:
                                   fm = files[file_id]
                                   if fm.deleted == false:
                                     for each t in new_tags:
                                       fm.tags.add(t)
                                       tagIndex[t].add(file_id)

4) Controller -> CLI:
     "ADD-TAGS result: success"
