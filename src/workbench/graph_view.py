from __future__ import annotations

from html import escape

from pyvis.network import Network


def render_case_graph_html(
    graph: dict,
) -> str:

    network = Network(
        height="720px",
        width="100%",
        directed=True,
        notebook=False,
        cdn_resources="in_line",
    )

    network.barnes_hut()


    for node in graph.get(
        "nodes",
        [],
    ):

        node_id = str(
            node["id"]
        )

        degree = int(
            node.get(
                "degree",
                1,
            )
        )

        focal = bool(
            node.get(
                "focal_endpoint",
                False,
            )
        )


        network.add_node(
            node_id,
            label=str(
                node.get(
                    "label",
                    node_id,
                )
            ),
            title=(
                f"Account: "
                f"{escape(node_id)}"
                f"<br>Displayed degree: "
                f"{degree}"
                f"<br>Focal endpoint: "
                f"{focal}"
            ),
            size=min(
                45,
                12 + degree * 2,
            ),
            shape=(
                "diamond"
                if focal
                else "dot"
            ),
        )


    for edge in graph.get(
        "edges",
        [],
    ):

        transaction_id = (
            edge.get(
                "transaction_id"
            )
        )

        amount = (
            edge.get(
                "amount"
            )
        )

        event_ts = (
            edge.get(
                "event_ts"
            )
        )

        focal = bool(
            edge.get(
                "is_focal",
                False,
            )
        )


        title = (
            f"Transaction: "
            f"{escape(str(transaction_id))}"
            f"<br>Amount: "
            f"{escape(str(amount))}"
            f"<br>Time: "
            f"{escape(str(event_ts))}"
            f"<br>Focal transaction: "
            f"{focal}"
        )


        network.add_edge(
            str(
                edge["source"]
            ),
            str(
                edge["target"]
            ),
            title=title,
            width=(
                5
                if focal
                else 1
            ),
        )


    network.set_options(
        """
        {
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
          },
          "physics": {
            "barnesHut": {
              "gravitationalConstant": -8000,
              "springLength": 160
            },
            "minVelocity": 0.75
          },
          "edges": {
            "arrows": {
              "to": {
                "enabled": true
              }
            },
            "smooth": {
              "enabled": true,
              "type": "dynamic"
            }
          }
        }
        """
    )


    return network.generate_html(
        notebook=False
    )
