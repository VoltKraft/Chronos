import { useCallback, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";

const initialNodes: Node[] = [
  { id: "start", type: "input", position: { x: 0, y: 0 }, data: { label: "Leave request submitted" } },
  { id: "delegate", position: { x: 240, y: 0 }, data: { label: "Delegate review" } },
  { id: "lead", position: { x: 480, y: 0 }, data: { label: "Team lead review" } },
  { id: "hr", position: { x: 720, y: 0 }, data: { label: "HR review" } },
  { id: "end", type: "output", position: { x: 960, y: 0 }, data: { label: "Approved" } },
];

const initialEdges: Edge[] = [
  { id: "e1", source: "start", target: "delegate" },
  { id: "e2", source: "delegate", target: "lead" },
  { id: "e3", source: "lead", target: "hr" },
  { id: "e4", source: "hr", target: "end" },
];

export default function WorkflowEditor() {
  const [nodes, setNodes] = useState<Node[]>(initialNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);

  const onNodesChange = useCallback((changes: NodeChange[]) => setNodes((ns) => applyNodeChanges(changes, ns)), []);
  const onEdgesChange = useCallback((changes: EdgeChange[]) => setEdges((es) => applyEdgeChanges(changes, es)), []);
  const onConnect = useCallback((c: Connection) => setEdges((es) => addEdge(c, es)), []);

  return (
    <div>
      <h1>Workflow editor</h1>
      <p style={{ color: "#666" }}>
        Placeholder canvas. Approval/scheduling workflows will be persisted as JSON (nodes + edges) and executed by the API.
      </p>
      <div style={{ height: 500, border: "1px solid #ddd" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
        >
          <Background />
          <MiniMap />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
