// types/chat.ts

import { ChartData } from './chart';

export interface ContentBlock {
  text?: string;
  toolUse?: ToolUse;
  toolResult?: ToolResult;
  json?: string;
}

export interface ToolUse {
  toolUseId: string;
  name: string;
  input: {
    [key: string]: any;
  };
}

export interface ToolResult {
  toolUseId: string;
  content: [{text?: string; json?: string;}];
  status?: 'success' | 'error'; 
}
export interface Visualization {
  chartType: string;
  chartData: any;
  chartTitle: string;
}

export interface Message {
  id: string;
  role: string;
  content: Array<{ text: string } | { image?: any } | { toolUse?: any } | { toolResult?: any }>;
  file?: FileUpload;
  visualization?: Visualization;
  timestamp?: string;
  technical_details?: {
    processing_time_sec?: number;
    processing_time_ms?: number;
    [key: string]: any; 
  };
}


export interface FileUpload {
  base64: string;
  fileName: string;
  mediaType: string;
  isText?: boolean;
  fileSize?: number;
}

export type Model = {
  id: string;
  name: string;
};

export interface APIResponse {
  content: string;
  hasToolUse: boolean;
  toolUse?: {
    type: "tool_use";
    id: string;
    name: string;
    input: ChartData;
  };
  chartData?: ChartData;
}

export interface AnalyzeAPIResponse {
  query?: string;
  explanation?: string;
  result?: any[];
  content: string;
  toolUseId?: string;
  toolName?: string;
  stopReason?: string;
  originalQuestion: string;
}