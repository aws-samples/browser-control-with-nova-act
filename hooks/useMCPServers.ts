"use client";
import { apiRequest } from '@/utils/api';
import { useState, useEffect } from "react";

export interface MCPServer {
  id: string;
  name: string;
  hostname: string;
  isActive: boolean;
  isConnected?: boolean;
}

export const useMCPServers = () => {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const fetchServers = async () => {
      try {
        setLoading(true);
        const response = await apiRequest('mcp-servers');
        if (!response.ok) throw new Error('Failed to fetch MCP servers');
        const data = await response.json();
        setServers(data);
      } catch (error) {
        console.error('Error fetching MCP servers:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchServers();
  }, []);

  const saveServers = async (updatedServers: MCPServer[]) => {
    try {
        const response = await apiRequest('mcp-servers', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(updatedServers),
          });
      
      if (!response.ok) throw new Error('Failed to save MCP servers');
      return true;
    } catch (error) {
      console.error('Error saving MCP servers:', error);
      return false;
    }
  };

  // Add new server
  const addServer = async (name: string, hostname: string) => {
    try {
      // Test server connection
      const testResult = await testServerConnection(hostname);
      
      if (testResult) {
        const newServer: MCPServer = {
          id: Date.now().toString(),
          name,
          hostname,
          isActive: true,
          isConnected: testResult,
        };
        
        const updatedServers = [...servers, newServer];
        setServers(updatedServers);
        await saveServers(updatedServers);
        
        return { success: true, server: newServer };
      } else {
        return { success: false, error: "Connection test failed" };
      }
    } catch (error) {
      return { success: false, error };
    }
  };

  // Remove server
  const removeServer = async (id: string) => {
    const updatedServers = servers.filter((server) => server.id !== id);
    setServers(updatedServers);
    await saveServers(updatedServers);
  };

  // Toggle server active status
  const toggleServerActive = async (id: string) => {
    const updatedServers = servers.map((server) =>
      server.id === id ? { ...server, isActive: !server.isActive } : server
    );
    setServers(updatedServers);
    await saveServers(updatedServers);
  };

  // Test server connection
  const testServerConnection = async (hostname: string): Promise<boolean> => {
    try {
        const response = await apiRequest('mcp-servers/test', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ hostname }),
          });
      
      const data = await response.json();
      return data.success;
    } catch (error) {
      console.error("Server connection test failed:", error);
      return false;
    }
  };

  // Retest server connection
  const retestServerConnection = async (id: string) => {
    const server = servers.find(s => s.id === id);
    if (!server) return false;

    try {
      const isConnected = await testServerConnection(server.hostname);
      
      const updatedServers = servers.map(s => 
        s.id === id ? { ...s, isConnected } : s
      );
      
      setServers(updatedServers);
      await saveServers(updatedServers);
      
      return isConnected;
    } catch (error) {
      return false;
    }
  };

  return {
    servers,
    loading,
    addServer,
    removeServer,
    toggleServerActive,
    testServerConnection,
    retestServerConnection
  };
};