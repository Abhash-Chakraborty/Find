"use client";

import React, { useState } from "react";

type AccountViewMode = "loading" | "no-instance-view" | "request-submitted" | "admin-dashboard" | "error";

export default function InstanceManagementPage() {
  const [currentView, setCurrentView] = useState<AccountViewMode>("no-instance-view");
  const [activeFormTab, setActiveFormTab] = useState<"join" | "create">("join");

  const [inviteToken, setInviteToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [instanceTitle, setInstanceTitle] = useState("");

  const [pendingRequests, setPendingRequests] = useState([
    { id: "1", user: "dev_alpha", contact: "alpha@team.local" },
    { id: "2", user: "engineer_beta", contact: "beta@team.local" },
  ]);
  const [activeDirectory, setActiveDirectory] = useState([
    { id: "admin", user: "System Administrator (You)", assignment: "Owner" },
  ]);

  const triggerApproval = (id: string, user: string) => {
    setPendingRequests(current => current.filter(item => item.id !== id));
    setActiveDirectory(current => [...current, { id, user, assignment: "Member" }]);
  };

  const triggerRejection = (id: string) => {
    setPendingRequests(current => current.filter(item => item.id !== id));
  };

  return (
    <div className="p-6 max-w-5xl mx-auto min-h-screen bg-white text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100 transition-colors duration-200">
      <header className="border-b pb-4 mb-6 border-zinc-200 dark:border-zinc-800">
        <h1 className="text-3xl font-bold tracking-tight">Shared Instance Administration</h1>
        <p className="text-sm mt-1 text-zinc-500 dark:text-zinc-400">
          Opt-in shared instance infrastructure and credential access control routing.
        </p>
      </header>

      <div className="mb-6 p-4 rounded-xl border bg-amber-50 text-amber-900 border-amber-200 dark:bg-amber-950/20 dark:text-amber-200 dark:border-amber-900/50">
        <h4 className="font-semibold flex items-center gap-2 text-sm">
          ⚠️ Privacy & Local-First Guardrails
        </h4>
        <p className="text-xs mt-1 leading-relaxed opacity-95">
          Resource sharing interfaces are entirely optional. Single-user system installations remain completely isolated locally. Setting up shared operations requires explicit administrator initialization and manual proxy deployment.
        </p>
      </div>

      {currentView === "loading" && (
        <div className="flex items-center justify-center py-12 gap-3">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
          <span className="text-sm text-zinc-400">Querying platform cluster instance records...</span>
        </div>
      )}

      {currentView === "error" && (
        <div className="p-4 border rounded-xl border-red-200 bg-red-50 text-red-900 dark:border-red-950/20 dark:text-red-200 dark:border-red-900/50 text-sm">
          <p className="font-semibold">Contextual Authorization Error</p>
          <p className="text-xs mt-1">An illegal session boundary handshake was encountered. Please log back into the client gateway.</p>
          <button onClick={() => setCurrentView("no-instance-view")} className="mt-3 px-3 py-1 bg-red-600 text-white rounded text-xs">Return to Panel</button>
        </div>
      )}

      {currentView === "no-instance-view" && (
        <div>
          <div className="flex gap-4 border-b border-zinc-200 dark:border-zinc-800 mb-6">
            <button 
              onClick={() => setActiveFormTab("join")}
              className={`pb-2 font-medium text-sm transition-all ${activeFormTab === "join" ? "border-b-2 border-blue-500 text-blue-600 dark:text-blue-400" : "text-zinc-400"}`}
            >
              Join Existing Team Instance
            </button>
            <button 
              onClick={() => setActiveFormTab("create")}
              className={`pb-2 font-medium text-sm transition-all ${activeFormTab === "create" ? "border-b-2 border-blue-500 text-blue-600 dark:text-blue-400" : "text-zinc-400"}`}
            >
              Setup Admin Instance Flow
            </button>
          </div>

          {activeFormTab === "join" ? (
            <div className="space-y-4 max-w-md p-6 border rounded-2xl border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-800/20">
              <div>
                <h3 className="text-lg font-medium">Instance Registry Form</h3>
                <p className="text-xs text-zinc-400">Connect to an active network hub entry point.</p>
              </div>
              <input 
                type="text" 
                placeholder="Invite Token or Shared Resource Link" 
                value={inviteToken}
                onChange={(e) => setInviteToken(e.target.value)}
                className="w-full p-2 text-sm border rounded bg-white dark:bg-zinc-800 border-zinc-300 dark:border-zinc-700" 
              />
              <div className="flex gap-2">
                <input 
                  type="text" 
                  placeholder="Username Token" 
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-1/2 p-2 text-sm border rounded bg-white dark:bg-zinc-800 border-zinc-300 dark:border-zinc-700" 
                />
                <input 
                  type="password" 
                  placeholder="Security Key Pass" 
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-1/2 p-2 text-sm border rounded bg-white dark:bg-zinc-800 border-zinc-300 dark:border-zinc-700" 
                />
              </div>
              <button 
                onClick={() => setCurrentView("request-submitted")}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium text-sm w-full transition-colors"
              >
                Dispatch Connect Request
              </button>
            </div>
          ) : (
            <div className="space-y-4 max-w-md p-6 border rounded-2xl border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-800/20">
              <div>
                <h3 className="text-lg font-medium">Deploy Cluster Master</h3>
                <p className="text-xs text-zinc-400">Configure decentralized sharing boundaries explicitly.</p>
              </div>
              <input 
                type="text" 
                placeholder="Instance Label (e.g., Development Team Node)" 
                value={instanceTitle}
                onChange={(e) => setInstanceTitle(e.target.value)}
                className="w-full p-2 text-sm border rounded bg-white dark:bg-zinc-800 border-zinc-300 dark:border-zinc-700" 
              />
              <button 
                onClick={() => setCurrentView("admin-dashboard")}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded font-medium text-sm w-full transition-colors"
              >
                Provision Instance
              </button>
            </div>
          )}
        </div>
      )}

      {currentView === "request-submitted" && (
        <div className="p-8 border rounded-2xl border-zinc-200 dark:border-zinc-800 text-center max-w-md mx-auto my-12 bg-zinc-50/50 dark:bg-zinc-800/10">
          <div className="text-3xl mb-3 animate-pulse">📡</div>
          <h3 className="text-xl font-bold">Registration Broadcasted</h3>
          <p className="text-sm mt-2 text-zinc-500 dark:text-zinc-400 leading-relaxed">
            Your secure request token has been buffered. Standby until the designated instance admin processes your access application pipeline.
          </p>
          <button onClick={() => setCurrentView("no-instance-view")} className="mt-5 text-xs text-blue-500 hover:underline">Cancel Gateway Request</button>
        </div>
      )}

      {currentView === "admin-dashboard" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="p-6 border rounded-2xl border-zinc-200 dark:border-zinc-800 bg-zinc-50/30 dark:bg-zinc-800/10">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Incoming Request Queue</h3>
              <span className="px-2 py-0.5 text-xs bg-zinc-200 dark:bg-zinc-700 rounded-full font-bold">{pendingRequests.length}</span>
            </div>
            {pendingRequests.length === 0 ? (
              <p className="text-sm text-zinc-400 dark:text-zinc-500 py-6 text-center">No structural registration tickets active.</p>
            ) : (
              <div className="space-y-3">
                {pendingRequests.map(item => (
                  <div key={item.id} className="p-3 border rounded-xl bg-white dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700 flex items-center justify-between shadow-sm">
                    <div>
                      <p className="text-sm font-medium">{item.user}</p>
                      <p className="text-xs text-zinc-400">{item.contact}</p>
                    </div>
                    <div className="flex gap-2">
                      <button 
                        onClick={() => triggerApproval(item.id, item.user)}
                        className="px-2.5 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-md transition-colors"
                      >
                        Approve
                      </button>
                      <button 
                        onClick={() => triggerRejection(item.id)}
                        className="px-2.5 py-1 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600 text-xs font-semibold rounded-md transition-colors"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="p-6 border rounded-2xl border-zinc-200 dark:border-zinc-800 bg-zinc-50/30 dark:bg-zinc-800/10">
            <h3 className="text-lg font-semibold mb-4">Instance Security Directory</h3>
            <div className="space-y-3">
              {activeDirectory.map(profile => (
                <div key={profile.id} className="p-3 border rounded-xl bg-white dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700 flex items-center justify-between shadow-sm">
                  <span className="text-sm font-medium">{profile.user}</span>
                  <span className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${profile.assignment === "Owner" ? "bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300" : "bg-green-100 text-green-800 dark:bg-green-950/60 dark:text-green-300"}`}>
                    {profile.assignment}
                  </span>
                </div>
              ))}
            </div>
            <button onClick={() => setCurrentView("no-instance-view")} className="mt-8 text-xs text-zinc-400 hover:text-zinc-200 flex items-center gap-1 transition-colors">
              ← Disconnect Dashboard Session
            </button>
          </div>
        </div>
      )}
    </div>
  );
}