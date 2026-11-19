export const desktop = ["overview","chats","content","account","tools","activity","settings"];
export const mobile = ["overview","chats","content","tools","more"];
export const more = ["account","activity","analytics","backups","automation","settings"];
export const areas = {
  chats:["chats","contacts","dialog_profiles","channels","groups","chat_detail"],
  content:["messages","media","saved","drafts","scheduled"],
  account:["profile","security","blocked_list"],
  tools:["cleanup","analytics","backups","automation"],
  settings:["settings","members"],
};

export function areaOf(section, parent) {
  if (section === "analytics" || section === "backups" || section === "automation") return "tools";
  if (section === "chat_detail" && parent === "cleanup") return "tools";
  return Object.keys(areas).find(area => areas[area].includes(section)) || section;
}
