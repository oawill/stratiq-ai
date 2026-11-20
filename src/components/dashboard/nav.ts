import {
  Activity,
  Beaker,
  Briefcase,
  FolderKanban,
  History,
  Landmark,
  LayoutGrid,
  LineChart,
  CreditCard,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";
import { brand } from "@/lib/brand";

export interface DashNav {
  label: string;
  href: string;
  icon: LucideIcon;
  keywords: string;
  status?: "live" | "soon";
}

export const DASH_NAV: DashNav[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutGrid, keywords: "home summary", status: "live" },
  { label: brand.products.sports.name, href: "/dashboard/sports", icon: Activity, keywords: "football soccer match fixtures poisson", status: "live" },
  { label: brand.products.strategy.name, href: "/dashboard/business", icon: Briefcase, keywords: "game theory nash payoff pricing", status: "live" },
  { label: brand.products.politics.name, href: "/dashboard/politics", icon: Landmark, keywords: "coalition voting power policy turnout", status: "live" },
  { label: brand.products.markets.name, href: "/dashboard/finance", icon: LineChart, keywords: "portfolio var risk monte carlo stress expected shortfall", status: "live" },
  { label: brand.products.simlab.name, href: "/dashboard/simulations", icon: Beaker, keywords: "monte carlo seed scenario", status: "live" },
  { label: "Prediction History", href: "/dashboard/history", icon: History, keywords: "forecasts past saved", status: "live" },
  { label: "My Workspace", href: "/dashboard/workspace", icon: FolderKanban, keywords: "team members organization", status: "live" },
  { label: "Team", href: "/dashboard/team", icon: Users, keywords: "members invite roles comments activity colleagues", status: "live" },
  { label: "Plan & Billing", href: "/dashboard/billing", icon: CreditCard, keywords: "subscription upgrade payment invoice stripe", status: "live" },
  { label: "Settings", href: "/dashboard/settings", icon: Settings, keywords: "account profile", status: "live" },
];
