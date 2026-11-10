import test from 'node:test';import assert from 'node:assert/strict';
import {publicationDate} from '../docs/publication_dates.js';
test('candidate pages show publication down to seconds with an explicit timezone',()=>{
 assert.equal(publicationDate({added_at:'2026-11-09T13:25:42.000Z',added_at_basis:'server receipt'}).text,'2026-11-09 13:25:42 UTC');
});
test('solve date never masquerades as repository publication',()=>{
 assert.match(publicationDate({solved_at:'2026-11-09T13:25:42Z'}).text,/Unknown/);
});
test('Git-backed curated history and live first receipt both work',()=>{
 assert.equal(publicationDate({id:'a'},{a:{added_at:'2026-11-01T03:00:04Z',basis:'first Git commit'}}).basis,'first Git commit');
 assert.equal(publicationDate({community_record:{added_at:'2026-11-09T13:25:42Z',received_at:'2026-11-10T00:00:00Z'}}).text,'2026-11-09 13:25:42 UTC');
 assert.match(publicationDate({received_at:'not a date'}).text,/Unknown/);
});
