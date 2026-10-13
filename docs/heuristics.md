# Assessing Placements

Checks run once per player on that player's final settlements (both draft
placements together). They are not evaluated turn by turn. A check is either
satisfied (`true`) or not (`false`) for that player.

## Checked

* **Access to complementary resource combinations.** Ore and wheat work well together, because they are the main ingredients for cities and development cards. Wood and brick support early expansion because both are needed for roads, and they are also half the cost of a new settlement. The heuristic (resource combos) is considered to be followed when the player’s settlements together include or and wheat, or wood and brick. The pieces may come from different settlements (e.g. wood on one and brick on the other) or from the same settlement. 
* **Proximity to a useful 2:1 port.**A resource-specific port is valuable when your placement is likely to produce that resource in excess. Being the player best positioned to claim the port also maters; its value falls if another player can reach it first. This heuristic (specific port) is considered to be followed by a player if such player is the one closest to a 2:1 port (ties count) and produces that port’s resource on a 5, 6, 8, or 9 tile.
* **Proximity to a 3:1 port when production is concentrated.** A generic port can turn repeated production of any one resource into a more balanced supply, even when no matching 2:1 port is available. This heuristic (generic port) is followed by a player when it is the closest to a 3:1 port (ties count) and has two or more tiles of one resource numbered among 4, 5, 6, 8, 9, 10. 
* **Number and quality of productive dice rolls.** Placements should be judged by both the probability of their numbers being rolled and how many distinct rolls produce something. Sixes and eights are the most frequent resource-producing rolls, followed by fives and nines; twos and twelves are rare. Distinct numbers are also safer than duplicate numbers 5/6/9 can produce on three rolls, whereas 6/6/9 is depending on rolling sixes. This heuristic (production) is considered followed by a player if its settlements combined give it access to tiles with four different numbers and the numbers are among 4, 5, 6, 8, 9, 10. 
* **Resource diversity.** Access to several resource types reduces dependance on player trades and makes more builds possible. For example, if a player has only access to wood, even if it comes from high probability tiles, they would need to rely on trades (perhaps expensive) with other players or the supply in order to make any progress. The heuristic (diversity) is considered to be followed by a player if their settlements combined give it access to tiles of at least 4 resource types. 

It may be impossible to satisfy every heuristic. Strong placements usually
balance production probability, strategic resource combinations, and realistic
opportunities to expand or trade.

## Not implemented

* **Potential for expansion.** Consider whether open neighboring intersections
  can be reached legally and whether opponents are likely to block the route.
  Expansion potential is especially useful when it leads to missing resources,
  stronger numbers, or a port. For example, an initial settlement with an
  uncontested two-road path to a strong wheat-and-ore intersection has more
  long-term value than one surrounded by occupied or easily contested spots.
