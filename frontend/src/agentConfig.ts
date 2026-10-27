export type FieldType = "text" | "textarea" | "number" | "checkbox";

export interface AgentField {
  name: string;
  label: string;
  type: FieldType;
  rows?: number;
  placeholder?: string;
}

export interface AgentConfig {
  slug: string;
  title: string;
  tagline: string;
  purpose: string;
  accent: string;
  features: string[];
  limitations: string[];
  fields: AgentField[];
  sample: Record<string, string | number | boolean>;
  repo: string;
}

export const agent: AgentConfig = {
  "slug": "plotxyz-cost-tracker-agent",
  "title": "Cost Tracker",
  "tagline": "See what AI and API usage actually costs.",
  "purpose": "Aggregates usage records by provider and model, computes total spend, compares against a budget, and flags overages.",
  "accent": "#f472b6",
  "features": [
    "Usage aggregation by provider and model",
    "Budget comparison and overage alerts",
    "Cost breakdown table"
  ],
  "limitations": [
    "Costs use user-supplied rates; actual provider bills may differ.",
    "No billing system is connected."
  ],
  "fields": [
    {
      "name": "usage",
      "label": "Usage records (JSON list)",
      "type": "textarea",
      "rows": 8,
      "placeholder": ""
    },
    {
      "name": "budget_usd",
      "label": "Monthly budget (USD)",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "usage": "[{\"model\":\"gpt-4\",\"provider\":\"openai\",\"tokens_in\":5000,\"tokens_out\":2000,\"calls\":120,\"rate_per_1k\":0.03},{\"model\":\"claude-3-haiku\",\"provider\":\"anthropic\",\"tokens_in\":12000,\"tokens_out\":3000,\"calls\":300,\"rate_per_1k\":0.0025},{\"model\":\"llama-3-8b\",\"provider\":\"ollama\",\"tokens_in\":8000,\"tokens_out\":4000,\"calls\":200,\"rate_per_1k\":0}]",
    "budget_usd": 50
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-cost-tracker-agent"
};
