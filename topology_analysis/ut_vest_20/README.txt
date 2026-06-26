2020 Utah precinct and election results shapefile.

## RDH Date retrieval
06/30/2021

## Sources
Election results from OpenElections (https://github.com/openelections/openelections-data-ut/tree/master/2020).
Precinct shapefile from Utah Automated Geographic Reference Center (https://gis.utah.gov/data/political/voter-precincts/).

## Fields metadata

Vote Column Label Format
------------------------
Columns reporting votes follow a standard label pattern. One example is:
G20PRERTRU
The first character is G for a general election, C for recount results, P for a primary, S for a special, and R for a runoff.
Characters 2 and 3 are the year of the election.
Characters 4-6 represent the office type (see list below).
Character 7 represents the party of the candidate.
Characters 8-10 are the first three letters of the candidate's last name.

Office Codes
AGR - Agriculture Commissioner
ATG - Attorney General
AUD - Auditor
COC - Corporation Commissioner
COU - City Council Member
DEL - Delegate to the U.S. House
GOV - Governor
H## - U.S. House, where ## is the district number. AL: at large.
INS - Insurance Commissioner
LAB - Labor Commissioner
LTG - Lieutenant Governor
PRE - President
PSC - Public Service Commissioner
SAC - State Appeals Court (in AL: Civil Appeals)
SCC - State Court of Criminal Appeals
SOS - Secretary of State
SSC - State Supreme Court
SPI - Superintendent of Public Instruction
TRE - Treasurer
USS - U.S. Senate

Party Codes
D and R will always represent Democrat and Republican, respectively.
See the state-specific notes for the remaining codes used in a particular file; note that third-party candidates may appear on the ballot under different party labels in different states.

## Fields
G20PRERTRU - Donald J. Trump (Republican Party)
G20PREDBID - Joseph R. Biden (Democratic Party)
G20PRELJOR - Jo Jorgensen (Libertarian Party)
G20PREGHAW - Howie Hawkins (Green Party)
G20PRECBLA - Don Blankenship (Constitution Party)
G20PREIPIE - Brock Pierce (Unaffiliated)
G20PREIWES - Kanye West (Unaffiliated)
G20PREIMCH - Joe McHugh (Unaffiliated)
G20PREILAR - Gloria La Riva (Unaffiliated)
G20PREOWRI - Write-in Votes

G20GOVRCOX - Spencer J. Cox (Republican Party)
G20GOVDPET - Chris Peterson (Democratic Party)
G20GOVLCOT - Daniel Rhead Cottam (Libertarian Party)
G20GOVADUE - Greg Duerden (Independent American Party)
G20GOVOWRI - Write-in Votes

G20ATGRREY - Sean D. Reyes (Republican Party)
G20ATGDSKO - Greg Skordas (Democratic Party)
G20ATGLBAU - Rudy J. Bautista (Libertarian Party)

G20AUDRDOU - John "Frugal" Dougall (Republican Party)
G20AUDCOST - Jeffrey L. Ostler (Constitution Party)
G20AUDUFAB - Brian L. Fabbi (United Utah Party)

G20TRERDAM - David Damschen (Republican Party)
G20TRELSPE - Joseph Speciale (Libertarian Party)
G20TRECPRO - Richard Proctor (Constitution Party)


## Processing Steps
The shapefile from the AGRC is of subprecincts, breaking down precincts in cases of district splits. In some cases, results are reported at the subprecinct level, in most cases, they weren't, so merging was done where necessary.
Emery County - 52 "canvas votes" were distributed to precincts.
