LIST FLOW
=========

CLI                         Controller
---                         ----------

1) User runs:
     list projectA report

2) CLI -> Controller:
     "LIST"
     - tag_query = ["projectA", "report"]

                            3) Controller:
                               - from tagIndex, get sets:
                                   S1 = tagIndex["projectA"]
                                   S2 = tagIndex["report"]
                               - compute intersection:
                                   S = S1 ∩ S2
                               - for each file_id in S:
                                   if files[file_id].deleted == false:
                                     collect:
                                       name  = files[file_id].name
                                       tags  = files[file_id].tags
                                       id    = file_id

4) Controller -> CLI:
     list of:
       - file_id
       - name
       - tags

5) CLI prints a table / list of results to the user.
