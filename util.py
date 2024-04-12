import networkx as nx
from networkx.classes import filters
import pandas as pd
import usaddress 
import probablepeople as pp 
import msgspec

# import requests 
# import msgspec 
# import json


def deduplicate_edges(G):
    records = [ {"source": edge[0], "target": edge[1], **edge[2]} for edge in G.edges(data=True) ]
    df = pd.DataFrame(records).drop_duplicates()
    source = df.source
    target = df.target
    attr = df.drop(columns=["source", "target"]).to_dict('records')
    G.clear_edges()
    G.add_edges_from(zip(source, target, attr))
    return G    

    
def get_alias_ids(G, nodes:list):
    full_list = []
    for n in nodes:
        try:
            full_list += G.nodes[n]['alias_ids']
        except Exception as e:
            full_list.append(n)
            
    return full_list 


def extract_name_parts(G:nx.MultiGraph):
    name_nodes = get_nodes_by_attribute(G, "tidy", "name")
    names_parts = {}
    for n in name_nodes:
        try:
            name = G.nodes[n]['label'].replace('.', '').strip().upper()
            parts = pp.parse(name)
            names_parts[n] = parts
        except Exception as e:
            print(e, n)
            continue
    
    records = []
    for name in names_parts:
        parts = names_parts[name]
        record = {part[1]: part[0].replace(',', '').replace('.', '') for part in parts}
        record["node_id"] = name
        if "CorporationName" not in record.keys():
            records.append(record)
    return pd.DataFrame(records).fillna('')


def extract_street_parts(G:nx.MultiGraph):
    street_nodes = get_nodes_by_attribute(G, "tidy", "address")
    records = []
    for n in street_nodes:
        try:         
            street = G.nodes[n]['label']
            tags = usaddress.tag(street.upper())
            records.append({"node_id": n, **tags[0]})
        except Exception as e:
            print(G.nodes[n])
            continue
    return pd.DataFrame(records).fillna('')


def combine_nodes(G, nodes:list):
    keep_node = nodes[0]
    for n in nodes:
        if n in G.nodes and n != keep_node:
            G = nx.identified_nodes(G, keep_node, n)
    G.nodes[keep_node]['alias_ids'] = nodes
    return G 


def tidy_up(G, ignore_middle_initial = True):
    nf = extract_name_parts(G)
    name_grouping = ['GivenName', 'Surname', 'SuffixGenerational'] if ignore_middle_initial else ['GivenName', 'MiddleInitial', 'Surname', 'SuffixGenerational']
    
    sr = extract_street_parts(G)
    street_grouping = ['AddressNumber', 'StreetName']
        
    nd = get_probable_duplicates(nf, name_grouping) if len(nf) > 0 else []
    sd = get_probable_duplicates(sr, street_grouping) if len(sr) > 0 else []
    duplicates = nd + sd
    for d in duplicates:
        G = combine_nodes(G, d)
    return G     


def get_probable_duplicates(df, grouping):
    grouping = [g for g in grouping if g in df.columns]
    probable_duplicates = (
        df
        .reset_index()
        .groupby(grouping)
        .agg({"node_id": ";".join, "index":"count"})
        .pipe(lambda df: df[df['index'] > 1])
    )
    return [pd.split(';') for pd in list(probable_duplicates.node_id)]


def combine_entitity_list(entity_lists:list):
    
    combined = entity_lists.pop()
    for e_list in entity_lists:
        ids = list(set([c.id for c in combined]))
        combined = combined + [e for e in e_list if e.id not in ids]
    
    return combined


def clean_columns(df:pd.DataFrame)->pd.DataFrame:
    lowercase = { 
        c: c.lower().strip().replace(' ', '_') 
        for c in df.columns }
    df = df.rename(columns=lowercase)
    return df.astype('str')


def get_edges(df, source, target, type):
    edges = list(df[[source, target, type]].dropna().to_records(index=False))
    edges = [ (e[0], e[1], {"type": e[2]}) for e in edges]
    return edges 


def get_nodes_by_attribute(G: nx.MultiGraph, key:str, filter_value:str) -> list:
    node_attributes = G.nodes(data=key, default = None)
    return [ n[0] for n in node_attributes if n[1] == filter_value ]


def get_edge_keys(G:nx.MultiGraph):
    edge_keys = set()
    for e in G.edges(data=True):
        edge_dict = e[2]
        edge_keys.update(edge_dict.keys())
    edge_keys.discard("type")
    return list(edge_keys)

def get_node_keys(G:nx.MultiGraph):
    node_keys = set()
    attributes = dict(G.nodes(data=True)).values()
    for a in attributes:
        for k in a.keys():
            if isinstance(a[k],(str, float, int)):
                node_keys.add(k)
    return list(node_keys)


def get_path_graph(G, node_1, node_2):
    path_nodes = set()
    shortest_paths = list(nx.all_shortest_paths(G.to_undirected(as_view=True), node_1, node_2))
    for path in shortest_paths:
        path_nodes.update(path)
    return nx.induced_subgraph(G, list(path_nodes))
  
  
def get_connected_nodes(G, node, nbrhood:dict = {}) -> dict:
    graph = G.to_undirected(as_view=True)
    if node in graph:
        nbrs = nx.neighbors(graph, node)
        nbrhood[node] = nbrs
        for n in nbrs:
            if n not in nbrhood:
                nbrhood.update(get_connected_nodes(graph, n, nbrhood))
        return nbrhood
    else:
        return nbrhood   
    
def get_node_names(G)->dict:
    node_names = {} 
    for n in G.nodes:
        name = G.nodes[n].get("label", n)
        node_names[name] = n
    
    return node_names