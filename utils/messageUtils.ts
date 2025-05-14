import { v4 as uuidv4 } from "uuid";
import type { Message, FileUpload } from '@/types/chat';

export const prepareApiMessages = (messages: Message[], userMessage?: Message) => {
  const messagesToProcess = userMessage ? [...messages, userMessage] : messages;
  
  return messagesToProcess.map((msg) => {
    if (msg.file) {
      const hasText = (content: any): content is { text: string } => {
        return 'text' in content && typeof content.text === 'string';
      };
      
      const textContent = msg.content.find(hasText);
      const textValue = textContent ? textContent.text : '';
      
      if (msg.file.isText) {
        const decodedText = decodeURIComponent(atob(msg.file.base64));
        return {
          role: msg.role,
          content: [{ text: `File contents of ${msg.file.fileName}:\n\n${decodedText}\n\n${textValue}` }]
        };
      } else {
        return {
          role: msg.role,
          content: [{
            image: {
              format: msg.file.mediaType.split('/')[1],
              source: {
                bytes: msg.file.base64
              }
            }
          }, 
          { text: textValue }
        ]};
      }
    }
    return {
      role: msg.role,
      content: msg.content 
    };
  });
};

export const createUserMessage = (text: string, file?: FileUpload, timestamp?: string): Message => ({
  id: uuidv4(),
  role: "user",
  content: [{ text }],
  file: file || undefined,
  timestamp: timestamp || new Date().toISOString()
});

export const createAssistantTextMessage = (text: string, timestamp?: string): Message => ({
  id: uuidv4(),
  role: "assistant",
  content: [{ text }],
  timestamp: timestamp || new Date().toISOString()
});

export const createSqlToolUseMessage = (toolUseId: string, query: string, explanation: string): Message => ({
  id: uuidv4(),
  role: "assistant",
  content: [
    {
      toolUse: {
        toolUseId,
        name: "generate_sql_query",
        input: {
          query,
          explanation
        }
      }
    }
  ]
});

export const createToolResultMessage = (toolUseId: string, result: any): Message => ({
  id: uuidv4(),
  role: "user",
  content: [
    {
      toolResult: {
        toolUseId,
        content: [
          {
            text: `Visualize this data: ${JSON.stringify(result)}`
          }
        ]
      }
    }
  ]
});

export const createErrorMessage = (errorText: string = "I apologize, but I encountered an error. Please try again.", timestamp?: string): Message => ({
  id: uuidv4(),
  role: "assistant",
  content: [{ text: errorText }],
  timestamp: timestamp || new Date().toISOString()
});

export const createVisualizationMessage = (text: string, visualization: any, timestamp?: string): Message => {
  const displayText = text || "Here's the visualization based on the data.";
  
  return {
    id: uuidv4(),
    role: "assistant",
    content: [{ text: displayText }],
    visualization: {
      chartType: visualization.chart_type || visualization.chart_data?.chartType || "bar",
      chartTitle: visualization.chart_title || visualization.chart_data?.config?.title || "Chart",
      chartData: visualization.chart_data
    },
    timestamp: timestamp || new Date().toISOString()
  };
};