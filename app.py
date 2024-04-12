import io 
import networkx as nx
from ipysigma import Sigma
from util import *
import pandas as pd 
import asyncio 
import msgspec
from collections import OrderedDict
from shiny import App, Inputs, Outputs, Session, reactive, render, ui, req
from shinywidgets import output_widget, render_widget
from shiny.types import FileInfo
from htmltools import TagList, div
from qng import GraphSchema, NodeFactory, LinkFactory, GraphFactory, SigmaFactory, Element, QNG



def download_handler():
    return file_buffer()

def accordion_item(title, content):
    return ui.accordion_panel(title, content)

def get_help(help_file:str):
    with open(f'help/{help_file}.md', 'r') as f:
        return ui.markdown(f.read())

help_accordion = {
    "Upload data": get_help("upload"),
    "Example (upload data)": get_help("upload_example")
}

acc_panels = [ accordion_item(key, help_accordion[key]) for key in help_accordion.keys() ]


question_circle =  ui.HTML('<i class="fa fa-question-circle" aria-hidden="true"></i>')

help_text = {
    "subgraph": ui.TagList(
                    ui.tags.p("Click a node on the graph or select some from the dropdown. The subgraph is anything connected to your selection."),
                    ui.tags.p("Preview to confirm it's what you want. Then you can delete it, or keep it and delete everything else.")
                ),
    "simple_paths": "Choose a starting point and and ending point and click 'Show' to see only nodes and edges that connect them. Click 'Clear' to return to the full graph.",
    "select": ui.TagList(ui.tags.p("Select node(s) by clicking on the graph and/or choosing from the dropdown."), ui.tags.p("Once selected, you can merge them together, remove them, or use them to search for more connections.")),
    "and_directly_connected": "in addition to what you selected, include any nodes directly linked to those nodes.",
    "merge_likely_duplicates": 'automatically merge nodes that are probably the same person/address - ("LASTNAME, FIRSTNAME JR" and "FIRSTNAME LASTNAME JR")',
    "name": "the name of a person or company. Use '%' as a wildcard", 
    "street": "the street address - exclude city/state/zip",
    "file_number": "corporate/llc file number, prefixed by CORP or LLC",
    "save/load_qng_graph_file": "Save a copy of this graph data in the Quick Network Graph (QNG) format, upload a graph you saved earlier, or upload one from Quick Network Graph at bit.ly/qng. Uploads are added to the current graph"
}

def tooltip(title:str):
    return ui.tooltip(
        ui.span(title, question_circle),
        help_text[title.lower().replace(" ", "_")],
        placement="right"
    )

def get_modal(title:str|None = None, prompt:str|ui.TagList|None = None, buttons:list = [], size = "m", easy_close=False):
    ui.modal_remove()
    return ui.modal(
        prompt, 
        title=title,
        size=size,
        footer=ui.TagList([b for b in buttons]) if len(buttons) > 0 else None,
        easy_close = False if len(buttons) > 0 else True
    )
    
    
### SHINY APP ###
# control_button_style = "width: 50%; margin:2px 2px 2px 2px;"

app_ui = ui.page_fillable(
    ui.head_content(ui.include_css("font-awesome-4.7.0 2/css/font-awesome.min.css")),
    
    ui.tags.style( """
        .accordion {margin 0px 0px 0px 0px;}
        .accordion-button {background-color:#f2f2f2 !important; }
        
        .fa-question-circle {margin: 0 0 0 5px}
        # .card-header {background-color: #ececec !important; }
        # ".card-divider {margin: 10px 0px 10px 0px !important;}
        # ".card-footer {justify-content: right; display: flex;}
        # ".checkbox {margin-top: 1rem;}
        # "#header_div { margin 0 0 0px 0px}
        
        #user_data {width: 100%;}
        #graph_cards .card-footer .btn {width: 50%; padding: 10px 0px 10px 0px; margin:100px 10px 10px 10px important!;}"  
        #create_link {margin-top: auto;}"  
        .card-footer .action-button {padding: 10px 0px 10px 0px; margin:100px 10px 10px 10px important!;}"    
    """ 
    ),
    ui.div(
        ui.layout_columns(
            ui.div(
                ui.h4("Quick Network Graphs", {"style": "margin: 0 0 0px 0px;"}),
                ui.a("A Public Data Tools project", href="http://publicdatatools.com"),
            ),
            ui.div(
                ui.help_text("Upload a spreadsheet, a QNG graph file, or a QNGS schema file"),
                ui.input_file("file1", "",accept=[".csv", ".xlsx", ".json", ".qng", ".qngs"], multiple=False, placeholder='XLSX, CSV, QNG', width="100%"),        
            ),
            col_widths=(7,5),
        ),
        id="header_div",
    ),
    
    ui.accordion(
        ui.accordion_panel("Data",            
            ui.layout_columns(
                ui.div(
                    ui.card(
                        ui.card_header("1. Add links (required)"),
                        ui.layout_columns(
                            ui.input_select("source_col", ui.TagList("Source", ui.help_text(" (connect this)")), choices = []),
                            ui.input_select("target_col",  ui.TagList("Target", ui.help_text(" (to this)")), choices = []),
                            ui.input_select("link_type_col", ui.TagList("Type", ui.help_text(" (column)")), choices=[]),
                            ui.input_text("link_type_txt", ui.TagList("Type", ui.help_text(" (description)")), placeholder=""),
                        ),
                        ui.card_footer(
                            ui.layout_columns(
                                ui.input_selectize("link_attrs", ui.TagList("Details (optional)", ui.br()), choices = [], multiple = True),
                                ui.input_action_button("create_link", "Add Link"),
                                col_widths=(6, -3, 3)
                            )
                        ),
                        id="link_inputs",
                    ),
                    ui.card(
                        ui.card_header("2. Add node details (optional)"),
                        ui.layout_columns(
                            ui.input_select("node_id_col", ui.TagList("ID", ui.help_text(" (what you link to)")), choices = []),
                            ui.input_select("node_label_col", ui.TagList("Label", ui.help_text(" (what you see)")), choices = []),
                            ui.input_select("node_type_col", ui.TagList("Type", ui.help_text(" (column)")), choices = []),    
                            ui.input_text("node_type_txt", ui.TagList("Type", ui.help_text(" (description)"))),
                        ),
                        ui.card_footer(
                            ui.layout_columns(
                                ui.input_selectize("node_attrs", ui.TagList("Details (optional)"), choices = [], multiple=True),
                                ui.div(
                                    ui.input_checkbox("is_name", "It's a name"),
                                    ui.input_checkbox("is_address", "It's an address"),
                                ),
                                ui.input_action_button("node_details", "Add Details"),
                                col_widths=(6, 3, 3)
                            ),
                        ),
                        fill=True
                    ),
                ),
                ui.card(
                    ui.card_header("3. Graph elements"),
                    "Links",
                    ui.output_data_frame("added_link_factories"),
                    "Nodes",
                    ui.output_data_frame("added_node_factories"), 
                    ui.card_footer(
                        ui.layout_columns(
                            ui.download_button("save_graph_schema", "Save Schema"),
                            ui.input_action_button("reset_schema", "Reset"),
                            ui.input_action_button("build_graph", "Build Graph")
                        ),
                    ),
                    fill=True
                ),
                col_widths = (7,5),
            ),
            ui.output_data_frame("user_data")    
        ),
        ui.accordion_panel("Graph", 
            ui.layout_columns(
                    ui.card(
                        ui.card_header("Select nodes"),
                        ui.layout_columns(
                            ui.div(
                                ui.input_selectize("selected_nodes", "", choices=[], multiple=True),                        
                                ui.input_checkbox("and_neighbors", "and connected nodes", value=False),
                                ui.input_checkbox("tidy", "merge likely duplicates", value=False),
                            ),
                            col_widths = (12),
                        ),
                        ui.card_footer(
                            ui.row(
                                ui.input_action_button("combine", "Merge"),
                                ui.input_action_button("remove", "Remove"),
                            ),
                        ),
                    ),
                    ui.card(
                        ui.card_header("Simple paths"), 
                        ui.layout_columns(
                                ui.input_select("path_start", "Start", choices = []),
                                ui.input_select("path_end", "End", choices = []),
                            col_widths=(6,6)
                        ),
                        ui.card_footer(
                            ui.row(
                                ui.input_action_button("clear_paths", "Clear"),
                                ui.input_action_button("show_paths", "Show"),
                            )
                        ),
                    ),
                    ui.card(
                        
                        ui.input_select("node_color_attribute", "Node color", choices = []),
                        ui.input_select("edge_size_attribute", "Edge size", choices = []),
                        ui.input_checkbox("show_all_labels", "Show all labels", value=False)
                    ),
                    ui.card(
                        ui.card_header(tooltip("Subgraph")),
                        ui.layout_column_wrap(
                                    ui.input_action_button("preview_subgraph", "Preview", class_="graph-control-button"),
                                    ui.input_action_button("keep_subgraph", "Keep", class_="graph-control-button"),
                                    ui.input_action_button("remove_subgraph", "Remove", class_="graph-control-button"),
                                    ui.input_action_button("cancel_subgraph", "Cancel", class_="graph-control-button"),    
                        width=(1/2),
                        fill=False,
                        ),
                    ),
                    ui.card(
                        ui.download_button("export_graph", "Export HTML"),
                        ui.download_button("save_graph_data", "Save Graph")
                    ),

                    col_widths = (3,3,2,2,2),
                    id = "graph_cards"
                ),
            ), 
                id="primary_accordion"
        ),
        output_widget("sigma_graph"),
        fillable=True
    )



def server(input, output, session):
        
    ### Reactive Values    
    frame = reactive.value(pd.DataFrame())
    filename = reactive.Value()
    
    link_factories = reactive.value([])
    lf_idx = reactive.value(None)
    
    node_factories = reactive.value({})
    G = reactive.value(nx.MultiDiGraph())
    SF = reactive.value(SigmaFactory())
    viz = reactive.value()
    
    nodes = reactive.value({})
    build_count = reactive.value(0)
    dropdowns = ["source_col", "target_col", "link_type_col", "link_attrs", "node_label_col", "node_id_col", "node_type_col", "node_attrs"]
    columns = reactive.value([])
    connected_nodes = reactive.value([])
    
    def get_selected_nodes():
        try:
            if viz().get_selected_node():
                selected = [ viz().get_selected_node() ]
            else:    
                selected = input.selected_nodes()

            neighbors = []
            if input.and_neighbors():
                for s in selected:
                    neighbors += list(G().neighbors(s))
                neighbors = list(set(neighbors))
                selected += neighbors
            return selected  
        except Exception as e:
            return []

    ### Load Files      
    @reactive.Effect
    @reactive.event(input.file1)
    def _():
        f: list[FileInfo] = input.file1()
        filetype = f[0]['type']
        filename.set(f[0]['name'])
        datapath = f[0]['datapath']
        
        if filetype == 'text/csv':
            df = pd.read_csv(datapath).pipe(clean_columns)
            frame.set(df)
        
        elif filename()[-5:] == ".xlsx":
            df = pd.read_excel(datapath).pipe(clean_columns)
            frame.set(df)
        
        elif filetype == "application/octet-stream":
            if filename()[-4:] == ".qng":
                load_graph_file(datapath)
                # ui.update_navs(id="main_panel", selected="Graph")
                # if len(graph) > 0:
                ui.update_accordion_panel(id="primary_accordion", target="Data", show=False)
                ui.update_accordion_panel(id="primary_accordion", target="Graph", show=True)
                viz.set(SF().make_sigma(G()))    
                
            elif filename()[-4:] == "qngs":
                load_schema_file(datapath)

    def load_schema_file(filename):
        with open(filename, 'r') as f:
            gs = graph_schema = msgspec.json.decode(f.read(), type=GraphSchema)
            link_factories.set(gs.link_factories)
            node_factories.set(gs.node_factories)                
            
            
    def load_graph_file(filename):
        with open(filename, 'r') as f:
            graph_data = msgspec.json.decode(f.read(), type=QNG)
        SF.set(graph_data.sigma_factory)
        
        if SF().edge_size:
            ui.update_select("edge_size_attribute", choices= [ None, *get_edge_keys(G())], selected = SF().edge_size)
        
        ui.update_select("node_color_attribute", choices = get_node_keys(G()), selected = SF().node_color)
        G.set( nx.compose(G(), graph_data.multigraph()) )

    
    @reactive.Effect 
    @reactive.event(input.upload_graph)
    def _():
        files: list[FileInfo] = input.upload_graph()
        for f in files:
            load_graph_file(f['datapath'])
        viz.set(SF().make_sigma(G()))    

            
    @reactive.Effect
    @reactive.event(input.reset_schema)
    def _():
        node_factories.set({})
        link_factories.set([])


    
    @reactive.Effect
    def update_column_lists():
        for box in dropdowns:        
            ui.update_selectize(box, choices=columns())

        
    @reactive.Effect
    @reactive.event(input.create_link)
    def _():
        
        # Figure out if the link type is a column or a description
        if len(input.link_type_col()) > 0:
            link_type = Element(type="field", value=input.link_type_col())
        elif len(input.link_type_txt()) > 0:
            link_type = Element(type="static", value=input.link_type_txt())
        else:
            link_type = Element(type="static", value=input.source_col())
        
        # Create the link factory
        lf = LinkFactory(
            source_field = input.source_col(),
            target_field = input.target_col(),
            type = link_type,
            attr = input.link_attrs()
        )
        
        # Add it to the graph elements
        link_factories.set(link_factories() + [lf])    

        # Create node factories for each node in the link
        for field in [lf.source_field, lf.target_field]:
            if field not in node_factories().keys():
                nf = NodeFactory(
                    id_field = field,
                    type = Element(type="static", value=field)
                )
                node_factories.set({**node_factories(), field: nf})
                                
        for box in ["source_col", "target_col"]:
            ui.update_selectize(box, choices = columns(), selected=None)
            
    @reactive.Effect
    @reactive.event(input.node_details)
    def _():
        if len(input.node_type_col()) > 0:
            node_type = Element(type="field", value=input.node_type_col())
        elif len(input.node_type_txt()) > 0:
            node_type = Element(type="static", value=input.node_type_txt())
        elif len(input.node_label_col()) > 0:
            node_type = Element(type="static", value=input.node_type_col())
        
        if len(input.node_label_col()) > 0:
            node_label = input.node_label_col()
        elif len(input.node_id_col()) > 0:
            node_label = input.node_id_col()
            
        if len(input.node_id_col()) > 0:
            node_id = input.node_id_col()
        elif len(input.node_label_col()) > 0:
            node_id = input.node_label_col()
        
        tidy = None
        if input.is_name():
            tidy = "name"
        if input.is_address():
            tidy = "address"
            
        nf = NodeFactory(
            id_field = node_id,
            label_field = node_label, 
            type = node_type,
            attr = input.node_attrs(), 
            tidy = tidy 
        )
        
        node_factories.set( { **node_factories(), **{node_id : nf} })
        for box in ["node_label_col", "node_id_col", "node_type_col"]:
            ui.update_select(box, choices = columns(), selected = None)
        ui.update_selectize("node_attrs", choices = columns(), selected = None)
        ui.update_text("node_type_txt", value= "")
        ui.update_checkbox("is_name", value=False)
        ui.update_checkbox("is_address", value=False)
        print("added node factory")


    ### Update input options / Enforce single inputs for type
    @reactive.Effect
    def _():
        columns.set([None, *sorted(list(frame().columns))])
         
    @reactive.Effect
    @reactive.event(input.link_type_col)
    def _():   
        if len(input.link_type_col()) > 0:
            ui.update_text(id="link_type_txt", value = "")
    
    @reactive.Effect
    @reactive.event(input.link_type_txt)
    def _():
        if len(input.link_type_txt()) > 0:
            ui.update_select(id="link_type_col", choices = columns(), selected = None)
                                
    @reactive.Effect
    @reactive.event(input.node_type_col)
    def _():
        if len(input.node_type_col()) > 0:
            ui.update_text(id="node_type_txt", value = "")        
        
    @reactive.Effect
    @reactive.event(input.node_type_txt)
    def _():
        if len(input.node_type_txt()) > 0:
            ui.update_select(id="node_type_col", choices = columns(), selected = None)
 
    @reactive.Effect
    @reactive.event(input.node_id_col)
    def _():
        if len(input.node_label_col()) == 0:
            ui.update_select(id="node_label_col", choices = columns(), selected = input.node_id_col())                       


    # graph option dropdowns
    @reactive.Effect 
    @reactive.event(G)
    def _():
         edge_keys = [ None, *get_edge_keys(G())]
         node_keys = get_node_keys(G())
         ui.update_select(id = "edge_size_attribute", choices=edge_keys, selected = None)
         ui.update_select(id = "node_color_attribute", choices=node_keys, selected = "type")


    ### Build the Graph
    @reactive.Effect
    @reactive.event(input.build_graph, input.tidy)
    def _():
        gf = GraphFactory(
            node_factories = node_factories().values(),
            link_factories = link_factories()
        )
        
        graph = G().copy()
        graph = nx.compose(graph, gf.make_graphs([row for row in frame().to_dict('records')], filename()))

        if input.tidy() is True and len(G()) > 0:
            graph = tidy_up(graph, ignore_middle_initial=True)
    
    
        G.set(graph)
        build_count.set( build_count() + 1 )
        if len(graph) > 0:
            ui.update_accordion_panel(id="primary_accordion", target="Data", show=False)
            ui.update_accordion_panel(id="primary_accordion", target="Graph", show=True)


    # Update SigmaFactory when style controls are updated 
    @reactive.Effect 
    @reactive.event(input.edge_size_attribute, input.node_color_attribute, input.clear_paths, input.show_all_labels)
    def _():
        
        params = SF().to_dict()        
        params = {p: params[p] for p in params if p not in ['edge_weight', 'edge_size', 'node_size']} # Reset edge sizes
        params["node_color"] = input.node_color_attribute()
        params["show_all_labels"] = input.show_all_labels()
        params["layout"] = viz().get_layout()

        if len(input.edge_size_attribute()) > 0:
            for n in G(): 
                G().nodes[n]['size'] = max(G().degree(n, input.edge_size_attribute()), 1)
                
            params['edge_weight'] = input.edge_size_attribute()
            params['edge_size'] = input.edge_size_attribute()
            params['clickable_edges'] = True
            params['node_size'] = 'size'
        SF.set(SigmaFactory(**params))


    @reactive.effect
    @reactive.event(G, SF) 
    def _():
        print("updating viz")
        try:
            layout = viz().get_layout()
            camera_state = viz().get_camera_state()
            viz.set(SF().make_sigma(G(), layout = layout, camera_state = camera_state))
        except Exception as e:
            print(e)
            viz.set(SF().make_sigma(G()))
            
    
    def get_connected_to_selected():
        selected = get_selected_nodes()
        connected = {}
        for s in selected:
            connected.update(get_connected_nodes(G(), s, connected))
        return connected 


    @reactive.effect
    @reactive.event(input.preview_subgraph)
    def _():
        if len(G()) > 0:
            connected = get_connected_to_selected()
            connected_nodes.set(connected)
            
            if len(connected) > 0:  
                selected_SF = SigmaFactory(
                    layout_settings = {"StrongGravityMode": False}, 
                    node_color_palette = None, 
                    node_color = lambda n: "selected" if n in connected else "not selected"
                )
                layout = viz().get_layout()
                camera_state = viz().get_camera_state()
                viz.set(selected_SF.make_sigma(G(), node_colors="Dark2", layout=layout, camera_state=camera_state))
            else:
                m = get_modal(
                    title="You didn't select anything",
                    prompt="Select a node by clicking it, or choose some from the selection dropdown. Then you can preview a subgraph of everything able to connect to your selection, and either remove it all, or keep it and remove everything else.",
                    buttons = [ui.modal_button("OK")]
                    )
                ui.modal_show(m)
                
    
    @reactive.effect
    @reactive.event(input.keep_subgraph)
    def _():
        connected = get_connected_to_selected()
        if len(connected) == 0 and len(connected_nodes()) > 0:
            connected = connected_nodes()
        graph = nx.induced_subgraph(G(), connected)
        G.set(graph)
        
    
    @reactive.effect
    @reactive.event(input.remove_subgraph)
    def _():
        connected = get_connected_to_selected()
        if len(connected) == 0 and len(connected_nodes()) > 0:
            connected = connected_nodes()
        graph = G().copy()
        graph.remove_nodes_from(connected)
        G.set(graph)
        
    @reactive.effect
    @reactive.event(input.cancel_subgraph, input.clear_paths)
    def _():
        graph = G().copy()
        G.set(graph)


    # Show Simple Paths
    @reactive.Effect
    @reactive.event(input.show_paths)        
    def _():
        print("generating path graph")
        PG = path_graph = get_path_graph(G(), input.path_start(), input.path_end())
        viz.set(SF().make_sigma(PG))

         
         
    ### OUTPUTS 
                
    @render.data_frame
    def user_data():
        return render.DataGrid(frame(), width="100%")
        
    @render.data_frame
    @reactive.event(link_factories) 
    def added_link_factories():
        return render.DataGrid(pd.DataFrame([lf.to_dict() for lf in link_factories()]), row_selection_mode="single")
    
    @render.data_frame 
    def added_node_factories():
        return render.DataGrid(pd.DataFrame([ node_factories()[nf].to_dict() for nf in node_factories() ]), row_selection_mode="single")
    
    # If a link factory is selected from Graph Elements, repopulate the input fields to match
    @reactive.effect 
    @reactive.event(input.added_link_factories_selected_rows)
    def _():
        selected_idx = list(req(input.added_link_factories_selected_rows())).pop()
        lf = link_factories().pop(selected_idx)
        new_link_factories = link_factories().copy()
        link_factories.set(new_link_factories)
        
        ui.update_select("source_col", choices = columns(), selected = lf.source_field)
        ui.update_select("target_col", choices = columns(), selected = lf.target_field)
        
        if lf.type.type == "static":
            ui.update_text("link_type_txt", value = lf.type.value)
            
        if lf.type.type == "field": 
            ui.update_select("link_type_col", choices = columns(), selected = lf.type.value)
        
        if lf.attr:
            ui.update_selectize("link_attrs", choices = columns(), selected = lf.attr)
            

    # If a node factory is selected from Graph Elements, repopulate the input fields to match            
    @reactive.effect 
    @reactive.event(input.added_node_factories_selected_rows)
    def _():
        selected_idx = list(req(input.added_node_factories_selected_rows())).pop()
        print(selected_idx)
        
        nf_keys = list(node_factories().keys())
        selected_key = nf_keys[selected_idx]
        nf = node_factories()[selected_key]
        ui.update_select("node_id_col", choices = columns(), selected = nf.id_field)
        
        if nf.label_field:
            ui.update_select("node_label_col", choices = columns(), selected = nf.label_field)
            
        if nf.type.type == "static":
            ui.update_text("node_type_txt", value = nf.type.value)
            
        if nf.type.type == "field": 
            ui.update_select("node_type_col", choices = columns(), selected = nf.type.value)
        
        if nf.attr:
            ui.update_selectize("node_attrs", choices = columns(), selected = nf.attr)
            
        if nf.tidy == "address":
            ui.update_checkbox("is_address", value=True)
        
        if nf.tidy == "name": 
            ui.update_checkbox("is_name", value=True)
        
        

    
    ### Remove selected nodes
    @reactive.effect
    @reactive.event(input.remove)
    def _():
        G().remove_nodes_from(get_selected_nodes())
    
    
    ### Merge selected nodes
    @reactive.effect
    @reactive.event(input.combine)
    def _():
        selected = get_selected_nodes()
        print("Merging", selected)
        new_graph = combine_nodes(G(), selected)
        G.set(new_graph)
      
      
    def update_node_choices(graph):
        node_names = get_node_names(graph)
        nodes.set(node_names)
        choices = {node_names[n]: n for n in sorted(list(node_names.keys()))}
            
        ui.update_selectize("selected_nodes", choices= choices)
        ui.update_select("path_start", choices=choices)
        ui.update_select("path_end", choices=choices)   

    
    @reactive.effect
    def _():
        update_node_choices(G())
    
    # Make graph widget
    @reactive.effect
    @reactive.event(G) 
    def _():
        try:
            layout = viz().get_layout()
            camera_state = viz().get_camera_state()
            viz.set(SF().make_sigma(G(), layout = layout, camera_state = camera_state))
        except Exception as e:
            print(e)
            viz.set(SF().make_sigma(G()))
    
    
    # Render graph 
    @render_widget(height="800px")
    @reactive.event(viz)
    def sigma_graph():
        return viz()
        
    @render.download(filename="graph_export.html")
    def export_graph():
        return SigmaFactory().export_graph(G())
    
    
    @render.download(filename="quick_network_graph.qng")
    def save_graph_data():
        adj = nx.to_dict_of_dicts(G())
        attrs = { n: G().nodes[n] for n in G().nodes()}
        qng = QNG(adjacency=adj, node_attrs=attrs, sigma_factory=SF())
        yield msgspec.json.encode(qng)
        
    
    @render.download(filename="graph_schema.qngs")
    def save_graph_schema():
        print(node_factories())
        print(link_factories())
        gs = GraphSchema(
                node_factories = node_factories(),
                link_factories = link_factories()
        )
        yield msgspec.json.encode(gs)

app = App(app_ui, server)