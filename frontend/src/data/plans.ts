// Single source of truth for plan pricing/features shown on the marketing
// page and during account creation — was previously hardcoded separately
// in Home.tsx alone, with no equivalent shown anywhere in the signup flow.
export interface PlanInfo {
  name: string;
  price: string;
  tagline: string;
  credits: string;
  highlight?: boolean;
  features: string[];
}

export const PLANS: PlanInfo[] = [
  {
    name: "Free",
    price: "$0",
    tagline: "Try it out",
    credits: "50 signup bonus credits",
    features: ["AI Content Studio, with automatic web research", "Buy extra credits directly"],
  },
  {
    name: "Pro",
    price: "$19",
    tagline: "For solo creators",
    credits: "1,000 credits/month",
    features: ["Everything in Free", "Calendar scheduling", "LinkedIn auto-publishing", "Credits marketplace (buy/sell)"],
  },
  {
    name: "Team",
    price: "$49",
    tagline: "For teams",
    credits: "5,000 credits/month",
    highlight: true,
    features: ["Everything in Pro", "Invite teammates by email", "Each member connects their own LinkedIn"],
  },
];
