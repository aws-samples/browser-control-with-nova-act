"use client";

import React, { useState } from "react";
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle 
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useMCPServers, MCPServer } from "@/hooks/useMCPServers";
import { AlertCircle, CheckCircle, Loader2, RefreshCw, Trash2 } from "lucide-react";

interface MCPServerSettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function MCPServerSettings({ isOpen, onClose }: MCPServerSettingsProps) {
  const { 
    servers, 
    addServer, 
    removeServer, 
    toggleServerActive,
    retestServerConnection 
  } = useMCPServers();
  
  const [newServerName, setNewServerName] = useState("");
  const [newServerHostname, setNewServerHostname] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isTestingServer, setIsTestingServer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAddServer = async () => {
    if (!newServerName || !newServerHostname) {
      setError("Please enter both server name and hostname.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const result = await addServer(newServerName, newServerHostname);
      if (result.success) {
        setNewServerName("");
        setNewServerHostname("");
      } else {
        setError("Failed to add server.");
      }
    } catch (err) {
      setError("An error occurred while adding server.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleServerTest = async (id: string) => {
    setIsTestingServer(id);
    try {
      await retestServerConnection(id);
    } finally {
      setIsTestingServer(null);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md md:max-w-lg">
        <DialogHeader>
          <DialogTitle>MCP Server Settings</DialogTitle>
          <DialogDescription>
            Manage MCP servers and test connections.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Adding MCP Server */}
          <div className="space-y-4 border-b pb-4">
            <h3 className="text-sm font-medium">Add New MCP Server</h3>
            
            <div className="grid grid-cols-1 gap-3">
              <div className="flex flex-col space-y-1.5">
                <Label htmlFor="server-name">Server Name</Label>
                <Input
                  id="server-name"
                  value={newServerName}
                  onChange={(e) => setNewServerName(e.target.value)}
                  placeholder="e.g. US West MCP Server"
                />
              </div>
              
              <div className="flex flex-col space-y-1.5">
                <Label htmlFor="server-hostname">Hostname</Label>
                <Input
                  id="server-hostname"
                  value={newServerHostname}
                  onChange={(e) => setNewServerHostname(e.target.value)}
                  placeholder="e.g. mcp-west.example.com:8080"
                />
              </div>

              {error && (
                <div className="text-sm text-red-500 flex items-center gap-1">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </div>
              )}

              <Button 
                onClick={handleAddServer} 
                disabled={isSubmitting}
                className="w-full"
              >
                {isSubmitting ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : null}
                Add and Test Server
              </Button>
            </div>
          </div>

          {/* Server List */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium">Registered MCP Servers</h3>
            {servers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No registered MCP servers.</p>
            ) : (
              <div className="space-y-3">
                {servers.map((server) => (
                  <div 
                    key={server.id} 
                    className="flex items-center justify-between p-3 border rounded-md"
                  >
                    <div className="flex items-center gap-3">
                      <Checkbox 
                        checked={server.isActive}
                        onCheckedChange={() => toggleServerActive(server.id)}
                        id={`server-${server.id}`}
                      />
                      <div className="space-y-0.5">
                        <Label 
                          htmlFor={`server-${server.id}`}
                          className="text-sm font-medium cursor-pointer"
                        >
                          {server.name}
                          {server.isConnected ? (
                            <span className="ml-2 text-xs text-green-600 inline-flex items-center">
                              <CheckCircle className="h-3 w-3 mr-1" />
                              Connected
                            </span>
                          ) : (
                            <span className="ml-2 text-xs text-red-600 inline-flex items-center">
                              <AlertCircle className="h-3 w-3 mr-1" />
                              Connection Failed
                            </span>
                          )}
                        </Label>
                        <p className="text-xs text-muted-foreground">{server.hostname}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleServerTest(server.id)}
                        disabled={isTestingServer === server.id}
                      >
                        {isTestingServer === server.id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <RefreshCw className="h-3 w-3" />
                        )}
                        <span className="sr-only">Test Connection</span>
                      </Button>
                      
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeServer(server.id)}
                        className="text-red-500 hover:text-red-700"
                      >
                        <Trash2 className="h-3 w-3" />
                        <span className="sr-only">Delete</span>
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button onClick={onClose}>Confirm</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
