import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import App from "./App";
import Login from "./pages/Login";
import WorkflowEditor from "./pages/WorkflowEditor";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Navigate to="/workflows" replace />} />
          <Route path="login" element={<Login />} />
          <Route path="workflows" element={<WorkflowEditor />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
