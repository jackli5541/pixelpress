from langgraph.graph import END, START, StateGraph

from pixelpress_backend.core.enums import LayoutDecision
from pixelpress_backend.graph.book_scoring_node import book_scoring_node
from pixelpress_backend.graph.chapter_clustering_node import chapter_clustering_node
from pixelpress_backend.graph.finalize_node import finalize_node
from pixelpress_backend.graph.layout_generation_node import layout_generation_node
from pixelpress_backend.graph.pagination_planning_node import pagination_planning_node
from pixelpress_backend.graph.photo_cleaning_node import photo_cleaning_node
from pixelpress_backend.graph.routing import score_router
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def build_layout_workflow():
    graph = StateGraph(LayoutWorkflowState)

    graph.add_node("photo_cleaning", photo_cleaning_node)
    graph.add_node("chapter_clustering", chapter_clustering_node)
    graph.add_node("pagination_planning", pagination_planning_node)
    graph.add_node("layout_generation", layout_generation_node)
    graph.add_node("book_scoring", book_scoring_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "photo_cleaning")
    graph.add_edge("photo_cleaning", "chapter_clustering")
    graph.add_edge("chapter_clustering", "pagination_planning")
    graph.add_edge("pagination_planning", "layout_generation")
    graph.add_edge("layout_generation", "book_scoring")
    graph.add_conditional_edges(
        "book_scoring",
        score_router,
        {
            LayoutDecision.ACCEPT.value: "finalize",
            LayoutDecision.RETRY_LAYOUT.value: "layout_generation",
            LayoutDecision.RETRY_PLANNING.value: "pagination_planning",
            LayoutDecision.RETRY_CHAPTER_CLUSTERING.value: "chapter_clustering",
        },
    )
    graph.add_edge("finalize", END)
    return graph.compile()


layout_workflow = build_layout_workflow()
