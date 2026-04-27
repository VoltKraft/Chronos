import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import "./styles.css";

import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { RequireAuth, RequireRole } from "./auth/RequireAuth";

import AuditPage from "./pages/AuditPage";
import ChangePassword from "./pages/ChangePassword";
import Dashboard from "./pages/Dashboard";
import LeaveInbox from "./pages/LeaveInbox";
import Login from "./pages/Login";
import MyLeave from "./pages/MyLeave";
import NewLeave from "./pages/NewLeave";
import PreferencesPage from "./pages/PreferencesPage";
import Reports from "./pages/Reports";
import ShiftCalendar from "./pages/ShiftCalendar";
import ShiftPlanner from "./pages/ShiftPlanner";
import UsersPage from "./pages/UsersPage";
import WorkflowEditor from "./pages/WorkflowEditor";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<App />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="login" element={<Login />} />
            <Route
              path="dashboard"
              element={
                <RequireAuth>
                  <Dashboard />
                </RequireAuth>
              }
            />
            <Route
              path="leave"
              element={
                <RequireAuth>
                  <MyLeave />
                </RequireAuth>
              }
            />
            <Route
              path="leave/new"
              element={
                <RequireAuth>
                  <NewLeave />
                </RequireAuth>
              }
            />
            <Route
              path="inbox"
              element={
                <RequireAuth>
                  <LeaveInbox />
                </RequireAuth>
              }
            />
            <Route
              path="shifts"
              element={
                <RequireAuth>
                  <ShiftCalendar />
                </RequireAuth>
              }
            />
            <Route
              path="preferences"
              element={
                <RequireAuth>
                  <PreferencesPage />
                </RequireAuth>
              }
            />
            <Route
              path="change-password"
              element={
                <RequireAuth>
                  <ChangePassword />
                </RequireAuth>
              }
            />
            <Route
              path="planner"
              element={
                <RequireRole roles={["team_lead", "hr", "admin"]}>
                  <ShiftPlanner />
                </RequireRole>
              }
            />
            <Route
              path="reports"
              element={
                <RequireRole roles={["team_lead", "hr", "admin"]}>
                  <Reports />
                </RequireRole>
              }
            />
            <Route
              path="users"
              element={
                <RequireRole roles={["hr", "admin"]}>
                  <UsersPage />
                </RequireRole>
              }
            />
            <Route
              path="audit"
              element={
                <RequireRole roles={["hr", "admin"]}>
                  <AuditPage />
                </RequireRole>
              }
            />
            <Route
              path="workflows"
              element={
                <RequireRole roles={["hr", "admin"]}>
                  <WorkflowEditor />
                </RequireRole>
              }
            />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
