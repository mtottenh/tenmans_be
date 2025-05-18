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
* [x] Add: Team Logo upload to 'register a team' dialog
    * [x] Add: Logo to Model
    * [x] Add: Logo to POST /teams/
    * [x] Add: Path for GET /teams/$id/logo
* [x] Add: Average ELO of roster to Team information page
* [x] Captains: Ability to make other team members as a captain
* [x] Captain: Ability to remove a player from the roster.
* [x] Captain: Ability to reject join request
* [ ] Captain: Ability to invite player
* [x] Player: Ability to cancle join request
* [ ] Captain: Not allowed to join another team
* [x] Player/Captain: Can't request to join more than one team
* [ ] Add: Past seasons results
* [ ] Add: Current season results.

### Open Questions
* [ ] Maximum active roster size?

## Players
* [x] Add Current/Best ELO to Player model
* [x] Add ability to scrape ELOs in the background
* [x] Add: Team/Roster & Team Logo to player page.
* [ ] Add: Roster history to player page.
* [x] Integrate: login/sign up via Steam
* [ ] Integrate:'link discord'
* [x] Add: Players dashboard to see all players in the league
* [x] Add: Search on players dashboard (captains get invite link to un-rostered players)
* [x] Add: Filter to players not on a roster.




#### New Data model integrations

* [x] Roster Service
* [x] Fixtures/Results
* Pugs
* Integrate the map picker state machines
* Go back and integrate the Audit module in all Services for actions that must be audited.
* Go back across all Routes and implement RBAC where nessecary
* Utils - Non Web based
    * [x] Creating an admin user (done sorta, not tested)
    * [x] Updating and displaying a users permissions/roles (done sorta, not tested)
    * [ ] Seeding a season
* Backups
* Migrations
    * Started ish?
* Upload service
* Map service
* State Service
* Add Redis to the Dockerfile.


* [ ] Map pool data modle & service rework
    * [ ] Map pool routes
    * [ ] Final map pool size - make configurable (default = 7)
* [ ] Permissions service Routes - currently only CLI tool, but global Admins should be able to use the service.
* [ ] Substitutes

* Tournament service:
    * [x]  Basic group stage generation
        * [ ] Add option for Home + Away v.s. Single matchup 
        * [ ] Configurable time between rounds 
        * 
    * Simple playoff bracket creation
* [ ] Fixture Service Routes
* [ ] Integration of Map picker into the fixture routes/service
* [ ] Server Data Model. 

* [ ] Admin routes need some work.
### Player API
* [~]  Add support for patching a player that registered through steam and has no email

### RCON API
* Need a separate web service that allows TLS Mutual Auth
    * Requires a valid client cert
    * 
* [ ] Add Tournament registration process mangement to the tournament sevice/routes


# 'Admin View'
* Requires Roles to be send to Front end
    * Requires Role Creation
        * Permission assignment to roles
* Bootstrapping initial role script
* Bootstrap initial admin user script
* Some way of logging in as an authenticated user (skip steam login flow)
* Assignment to USER role on player creation
* Return list of roles in player endpoins
    * Make front-end key of 'is-admin' in returned role list.


# Team creation
    - Requires Season Service/APIS
        - Requires MGMT interface to create seasons
        - Requires RBAC to be implemented properly
            - Requires RBAC service implementation
            - Requires RBAC API endpoints


### Deletion
* Implement soft deletes for all resource types.
    * Players
    * Teams
    * Maps
    * Tournaments
    * Seasons
    * Fixtures
    




# TODO
    * Team Service Migrate archive_team to new status transition pipeline.
* Implement link_tournaments
    * This should probably be an audited transaction.
* Tournament Service should refactor complete round to use the existing generate_round_fixtures function and pipeline stpes?