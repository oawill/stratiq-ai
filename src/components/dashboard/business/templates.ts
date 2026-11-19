export interface Template {
  id: string;
  name: string;
  blurb: string;
  players: [string, string];
  rows: string[];
  cols: string[];
  payoffs: number[][][];
}

// Illustrative textbook / hypothetical games. The numbers are made up for teaching; they are not market data.
export const TEMPLATES: Template[] = [
  {
    id: "pd", name: "Prisoner's dilemma (price war)", blurb: "Each firm gains by undercutting, yet both are worse off than if they held prices.",
    players: ["Firm A", "Firm B"], rows: ["Hold price", "Undercut"], cols: ["Hold price", "Undercut"],
    payoffs: [[[3, 3], [0, 5]], [[5, 0], [1, 1]]],
  },
  {
    id: "bos", name: "Coordination (battle of the sexes)", blurb: "Two compatible-standard choices; both prefer to match but disagree on which.",
    players: ["Firm A", "Firm B"], rows: ["Standard X", "Standard Y"], cols: ["Standard X", "Standard Y"],
    payoffs: [[[2, 1], [0, 0]], [[0, 0], [1, 2]]],
  },
  {
    id: "mp", name: "Matching pennies (no pure equilibrium)", blurb: "One side wants to match, the other to mismatch.",
    players: ["Matcher", "Mismatcher"], rows: ["Heads", "Tails"], cols: ["Heads", "Tails"],
    payoffs: [[[1, -1], [-1, 1]], [[-1, 1], [1, -1]]],
  },
  {
    id: "entry", name: "Market entry", blurb: "An entrant decides whether to enter; the incumbent decides whether to fight.",
    players: ["Entrant", "Incumbent"], rows: ["Enter", "Stay out"], cols: ["Fight", "Accommodate"],
    payoffs: [[[-2, 0], [3, 3]], [[0, 5], [0, 5]]],
  },
  {
    id: "duopoly", name: "Pricing duopoly (3 price levels)", blurb: "Profits computed from the landing-page demo model (unit cost $5, $1,500 fixed cost). Hypothetical assumptions, not market data.",
    players: ["Company A", "Company B"], rows: ["Low ($8)", "Medium ($12)", "High ($16)"], cols: ["Low ($8)", "Medium ($12)", "High ($16)"],
    payoffs: [[[300, 300], [942, 502], [1440, -1280]], [[502, 942], [2000, 2000], [3162, 1074]], [[-1280, 1440], [1074, 3162], [2900, 2900]]],
  },
];
