// Curated associations from data/celestia_addons.json. Exact IDs prevent linking unrelated routes.
export const MISSION_ADDONS = [
  {
    "title": "Eris Explorer",
    "source_url": "https://celestia.mobi/resources/item/1955C443-C52C-419B-9736-6703F37ADE65",
    "mission_ids": [
      "d62eda751aba894c5777c532e8c2267b2ff3a3999bc185e3849ffdad50bb9bbf"
    ]
  },
  {
    "title": "Tianwen-4",
    "source_url": "https://celestia.mobi/resources/item/45B5EB94-2DE1-429B-B39E-4326DB7EA7F5",
    "mission_ids": [
      "tianwen4-concept"
    ]
  },
  {
    "title": "Uranus Orbiter and Probe",
    "source_url": "https://celestia.mobi/resources/item/6723285F-79DA-4696-AF4F-0D8948A84573",
    "mission_ids": [
      "claudius-uop-2045",
      "61a83e8f369c"
    ]
  },
  {
    "title": "INFINITY",
    "source_url": "https://celestia.mobi/resources/item/BB56D66D-38AC-4712-ACB5-492916136ED3",
    "mission_ids": [
      "c16155480c4d"
    ]
  }
];
export function missionAddons(candidate,resolve=id=>id){
 const ids=new Set([candidate?.id,candidate?.community_record?.id,candidate?.provenance?.candidate_id].filter(Boolean));
 return MISSION_ADDONS.filter(addon=>addon.mission_ids.some(id=>(ids.has(id)||ids.has(resolve(id)))));
}
export function appendMissionAddons(container,candidate,resolve){
 for(const addon of missionAddons(candidate,resolve)){
  const a=document.createElement('a');a.className='text-link small';a.textContent='Celestia addon · '+addon.title+' ↗';
  a.href=addon.source_url;a.target='_blank';a.rel='noopener noreferrer';container.append(a);
 }
}
