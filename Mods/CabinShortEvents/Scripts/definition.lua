return {id="cabin_short_events",name="CabinShortEvents",hint="Task size: 100% = original, lower = shorter",fields={
    {key="enabled",label="Enabled",type="boolean",default=true,host=true},
    {key="balloon_factor",label="Balloon task size",type="number",display="percent",default=2/3,min=0.01,positive=true,max=1,host=true},
    {key="train_factor",label="Train task size",type="number",display="percent",default=2/3,min=0.01,positive=true,max=1,host=true},
}}
