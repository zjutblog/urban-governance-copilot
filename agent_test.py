from app.workflow.graph import build_graph

from app.domain.complaint import Complaint



graph = build_graph()



complaint = Complaint(

    complaint_id="001",

    content=
    """
    小区附近晚上施工，
    每天凌晨噪音很大，
    希望有关部门处理。
    """,

    province="浙江",

    city="杭州",

    field="环境"

)



state={

"complaint":complaint,

"analysis":None,

"decision":None,

"retrieved_documents":[],

"review":None,

"current_step":"start",

"next_action":None,

"trace":[],

"tool_calls":[],

"errors":[],

"evaluation":None

}



result = graph.invoke(
    state
)



print("=================")

print(result)