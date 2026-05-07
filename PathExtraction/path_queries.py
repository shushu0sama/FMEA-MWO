# This file contains the cypher queries for Neo4j to extract paths

# isA relationships: PhysicalObject, Property, Process, State, Activity
PO_MATCH =  "OPTIONAL MATCH (o)-[:isA*]->(substitute_objects:PhysicalObject)"
PO_RETURN = "collect(properties(substitute_objects)) AS substitute_objects"

PP_MATCH =  "OPTIONAL MATCH (p)-[:isA*]->(substitute_property:Property)"
PP_RETURN = "collect(properties(substitute_property)) AS substitute_property"

PC_MATCH =  "OPTIONAL MATCH (p)-[:isA*]->(substitute_process:Process)"
PC_RETURN = "collect(properties(substitute_process)) AS substitute_process"

ST_MATCH =  "OPTIONAL MATCH (s)-[:isA*]->(substitute_state:State)"
ST_RETURN = "collect(properties(substitute_state)) AS substitute_state"

AT_MATCH =  "OPTIONAL MATCH (a)-[:isA*]->(substitute_activity:Activity)"
AT_RETURN = "collect(properties(substitute_activity)) AS substitute_activity"

# Path queries
direct_queries = [
    { # Query 1: Find all OBJECT with undesirable properties
        "query": f"""MATCH (o:PhysicalObject)-[:hasProperty]->(p:Property {{subtype0: "UndesirableProperty"}}) {PO_MATCH} {PP_MATCH}
                    RETURN properties(o) AS object_properties, properties(p) AS property_properties, {PO_RETURN}, {PP_RETURN}
                """,
        "outfile": "object_property_paths",
        "event": "property",
        "relation": "hasProperty"
    },
    { # Query 2: Find all undesirable processes with AGENTS OBJECT
        "query": f"""
                    MATCH (p:Process {{subtype0: 'UndesirableProcess'}})-[:hasParticipant_hasAgent]->(o:PhysicalObject) {PO_MATCH} {PC_MATCH}
                    RETURN properties(o) AS object_properties, properties(p) AS process_properties, {PO_RETURN}, {PC_RETURN}
                """,
        "outfile": "process_agent_paths",
        "event": "process",
        "relation": "hasAgent"
    },
    { # Query 3: Find all undesirable processes with PATIENTS OBJECT
        "query": f"""
                    MATCH (p:Process {{subtype0: 'UndesirableProcess'}})-[:hasParticipant_hasPatient]->(o:PhysicalObject) {PO_MATCH} {PC_MATCH}
                    RETURN properties(o) AS object_properties, properties(p) AS process_properties, {PO_RETURN}, {PC_RETURN}
                """,
        "outfile": "process_patient_paths",
        "event": "process",
        "relation": "hasPatient"
    },
    { # Query 4: Find all undesirable states with PATIENTS OBJECT
        "query": f"""
                    MATCH (s:State {{subtype0: 'UndesirableState'}})-[:hasParticipant_hasPatient]->(o:PhysicalObject) {PO_MATCH} {ST_MATCH}
                    RETURN properties(o) AS object_properties, properties(s) AS state_properties, {PO_RETURN}, {ST_RETURN}
                """,
        "outfile": "state_patient_paths",
        "event": "state",
        "relation": "hasPatient"
    }
]

complex_queries = [
    { # Query 5: Find all OBJECT with PROPERTIES linked to undesirable states
        "query": f"""
                    MATCH (o:PhysicalObject)-[:hasProperty]->(p:Property)
                    MATCH (s:State {{subtype0: 'UndesirableState'}})-[:hasParticipant_hasPatient]->(p) {PO_MATCH} {PP_MATCH} {ST_MATCH}
                    RETURN properties(o) AS object_properties, properties(p) AS property_properties, properties(s) AS state_properties, {PO_RETURN}, {PP_RETURN}, {ST_RETURN}
                """,
        "outfile": "object_property_state_paths",
        "event": "property",
        "helper": "state",
        "relation": "hasProperty"
    },
    { # Query 6: Find all OBJECT with PROCESSES linked to undesirable states
        "query": f"""
                    MATCH (o:PhysicalObject)-[:hasParticipant_hasPatient]->(p:Process)
                    MATCH (s:State {{subtype0: 'UndesirableState'}})-[:hasParticipant_hasPatient]->(p) {PO_MATCH} {PC_MATCH} {ST_MATCH}
                    RETURN properties(o) AS object_properties, properties(p) AS process_properties, properties(s) AS state_properties, {PO_RETURN}, {PC_RETURN}, {ST_RETURN}
                """,
        "outfile": "object_process_state_paths",
        "event": "process",
        "helper": "state",
        "relation": "hasPatient"
    },
    { # Query 7: Find all undesirable states with agents OBJECT where states linked to activities
        "query": f"""
                    MATCH (s:State {{subtype0: 'UndesirableState'}})-[:hasParticipant_hasAgent]->(o:PhysicalObject)
                    MATCH (s)-[:hasParticipant_hasPatient]->(a:Activity) {PO_MATCH} {ST_MATCH} {AT_MATCH}
                    RETURN properties(o) AS object_properties, properties(s) AS state_properties, properties(a) AS activity_properties, {PO_RETURN}, {ST_RETURN}, {AT_RETURN}
                """,
        "outfile": "state_agent_activity_paths",
        "event": "state",
        "helper": "activity",
        "relation": "hasAgent"
    },
    { # Query 8: Find all undesirable states with agents OBJECT where states have patient OBJECT
        "query": f"""
                    MATCH (s:State {{subtype0: 'UndesirableState'}})-[:hasParticipant_hasAgent]->(o:PhysicalObject)
                    MATCH (s)-[:hasParticipant_hasPatient]->(o2:PhysicalObject) {PO_MATCH} {ST_MATCH} 
                    RETURN properties(o) AS object_properties, properties(s) AS state_properties, properties(o2) AS patient_properties, {PO_RETURN}, {ST_RETURN}
                """,
        "outfile": "state_agent_patient_paths",
        "event": "state",
        "helper": "patient",
        "relation": "hasAgent"
    },
    { # Query 9: Find all undesirable processes with agents OBJECT where processes have patient OBJECT
        "query": f"""
                    MATCH (p:Process {{subtype0: 'UndesirableProcess'}})-[:hasParticipant_hasAgent]->(o:PhysicalObject)
                    MATCH (p)-[:hasParticipant_hasPatient]->(o2:PhysicalObject) {PO_MATCH} {PC_MATCH}
                    RETURN properties(o) AS object_properties, properties(p) AS process_properties, properties(o2) AS patient_properties, {PO_RETURN}, {PC_RETURN}
                """,
        "outfile": "process_agent_patient_paths",
        "event": "process",
        "helper": "patient",
        "relation": "hasAgent"
    }
]

# ============================================================
# Chinese FMEA KG queries (中文故障模式与影响分析知识图谱)
# ============================================================

cn_direct_queries = [
    {   # Query CN-1: 系统 → 故障模式 → 故障起因
        "query": """
            MATCH (s:关注要素层次)-[:故障模式]->(m:故障模式)-[:故障起因]->(c:故障起因)
            WHERE s.name IS NOT NULL AND m.name IS NOT NULL AND c.name IS NOT NULL
            RETURN s.name AS system, m.name AS failure_mode, c.name AS cause,
                   '故障起因' AS path_type
        """,
        "outfile": "cn_system_failure_cause",
        "path_type": "direct",
        "object_field": "cause",
        "event_field": "failure_mode"
    },
    {   # Query CN-2: 故障模式 → 故障影响
        "query": """
            MATCH (m:故障模式)-[:故障影响]->(e:故障影响)
            WHERE m.name IS NOT NULL AND e.name IS NOT NULL
            RETURN m.name AS failure_mode, e.name AS effect,
                   '故障影响' AS path_type
        """,
        "outfile": "cn_failure_effect",
        "path_type": "direct",
        "object_field": "effect",
        "event_field": "failure_mode"
    },
    {   # Query CN-3: 系统 → 组件层次
        "query": """
            MATCH (s:关注要素层次)-[:下一低分析层次]->(c:下一低分析层次)
            WHERE s.name IS NOT NULL AND c.name IS NOT NULL
            OPTIONAL MATCH (c)-[:下一低层次功能]->(f:下一低层次功能)
            RETURN s.name AS system, c.name AS component, f.name AS function,
                   '组件层次' AS path_type
        """,
        "outfile": "cn_system_component",
        "path_type": "direct",
        "object_field": "component",
        "event_field": "system"
    },
]

cn_complex_queries = [
    {   # Query CN-4: 系统 → 故障模式 → 全链路（起因+影响+预防+探测）
        "query": """
            MATCH (s:关注要素层次)-[:故障模式]->(m:故障模式)
            WHERE s.name IS NOT NULL AND m.name IS NOT NULL
            WITH s, m
            OPTIONAL MATCH (m)-[:故障起因]->(c:故障起因)
            WITH s, m, c
            LIMIT 500
            RETURN s.name AS system, m.name AS failure_mode,
                   c.name AS cause, '全链路' AS path_type
        """,
        "outfile": "cn_full_chain",
        "path_type": "complex",
        "object_field": "system",
        "event_field": "failure_mode"
    },
    {   # Query CN-5: 故障模式 → 预防控制措施 (用于纠正性维护)
        "query": """
            MATCH (m:故障模式)-[:预防控制措施]->(p:预防控制措施)
            WHERE m.name IS NOT NULL AND p.name IS NOT NULL
            RETURN m.name AS failure_mode, p.name AS prevention,
                   '预防措施' AS path_type
        """,
        "outfile": "cn_prevention",
        "path_type": "complex",
        "object_field": "prevention",
        "event_field": "failure_mode"
    },
    {   # Query CN-6: 功能 → 故障模式 (功能失效路径)
        "query": """
            MATCH (s:关注要素层次)-[:功能]->(f:功能)
            MATCH (s)-[:故障模式]->(m:故障模式)
            WHERE f.name IS NOT NULL AND m.name IS NOT NULL
            RETURN s.name AS system, f.name AS function, m.name AS failure_mode,
                   '功能失效' AS path_type
        """,
        "outfile": "cn_function_failure",
        "path_type": "complex",
        "object_field": "function",
        "event_field": "failure_mode"
    },
]

# Function to return recursive hasPart/contains PhysicalObjects
def get_connect_objects(driver, entity):
    """ Return recursive hasPart/contains PhysicalObjects """
    query = f"""
                MATCH path = (a:PhysicalObject)-[:hasPart|contains*]->(b:PhysicalObject {{text: "{entity}"}})
                WITH [n IN nodes(path) | n.text] AS connect_objects
                RETURN connect_objects
            """
    connect_objects = []
    with driver.session() as session:
        results = session.run(query)
        for record in results:
            # Remove last entity and reverse the list
            object_list = record["connect_objects"][:-1]
            connect_objects.append(object_list[::-1])
    return connect_objects

# Function to return failure mode of an entry entity
def get_failure_mode(driver, entry_id):
    """ Return failure mode of an entry entity """
    query = f"""
                MATCH (e:Entry {{id: {entry_id}}})
                RETURN e.failure_mode AS failure_mode
            """
    with driver.session() as session:
        results = session.run(query)
        record = results.single()
        if record:
            return record["failure_mode"]
        return None