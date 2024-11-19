# Things Left to do

## Utils
* [x] Add a tool to create admin accounts (Admins)

## Admins
* [x] Add a page to create a new season
* [ ] Create a dashboard on the page which lists the season's teams with active rosters
* [x] Create a button to lock the teams and generate the group stage
    * [ ] Rosters locked if group stage has started.
* [ ] Strech goal - add a 'late team registration' process?
* [ ] Add the ability to ban/remove a team from a season, this should delete the fixtures for (team_id,season_id)
    * E.g. if a team gets banned
* [ ] Add ability to ban a player

### Open questsions
    * Ask Jiffz if he wans an 'open roster' during groups?

## Seasons
* [ ] Restrict the Season create API to Admins only
* [ ] Add APIs to remove a season (remove cruft/clutter? maybe keep in the DB but mark as stale?)
* [x] Display team logo's in the season league table

## Fixtures
* [x] Restrict ability to add a result to Team Captains only
* [x] Add result confirmation process
* [x] Use confirmation process in fixture page
* [ ] Add: Admin view of fixture page
* [ ] Add: Result evidence upload
* [ ] Add: Editing of result & evidence until confirmation has taken place.
* [ ] Optional - demo picker?
* [ ] Confirming a result should check to see whether all fixtures in the round have been played, and advance the knockout rounds.

## Teams
* [ ] Should we restrict team creation?
* [ ] Add: Team Logo upload to 'register a team' dialog
    * [x] Add: Logo to Model
    * [x] Add: Logo to POST /teams/
    * [x] Add: Path for GET /teams/$id/logo
* [ ] Add: Average ELO of roster to Team information page
* [ ] Captains: ability to make other team members as a captain
* [ ] Captain: Ability to remove a player from the roster.
* [ ] Captain: Ability to reject join request
* [ ] Captain: Add ability to invite player
* [ ] Player: Ability to cancle join request
* [ ] Captain: Not allowed to join another team
* [ ] Player/Captain: Can't request to join more than one team
* [ ] Add: Past seasons results
* [ ] Add: Current season results.

### Open Questions
* [ ] Maximum active roster size?

## Players
* [ ] Add Current/Best ELO to Player model
* [ ] Add ability to scrape ELOs in the background
* [ ] Add: Team/Roster & Team Logo to player page.
* [ ] Add: Roster history to player page.
* [ ] Integrate: login/sign up via Steam
* [ ] Integrate:'link discord'
* [ ] Add: Players dashboard to see all players in the league
* [ ] Add: Search on players dashboard (captains get invite link to un-rostered players)
* [ ] Add: Filter to players not on a roster.
