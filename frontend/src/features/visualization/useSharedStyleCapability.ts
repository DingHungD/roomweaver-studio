import {useEffect,useState} from 'react';

// A page can be rebuilt while its local Python service is still an older
// version. Do not submit fields that that process cannot validate yet.
export function useSharedStyleCapability(){
  const [ready,setReady]=useState(false);
  useEffect(()=>{let active=true,timer:ReturnType<typeof setTimeout>;const controller=new AbortController();
    async function check(){let supported=false;try{
      const response=await fetch('/openapi.json',{signal:controller.signal});
      if(response.ok){const schema=await response.json();supported=!!schema.components?.schemas?.ObjectGroup?.properties?.style_prompt;}
    }catch{/* Keep existing editing available while the service is restarting. */}
      if(!active)return;setReady(supported);if(!supported)timer=setTimeout(()=>void check(),5000);
    }
    void check();return()=>{active=false;clearTimeout(timer);controller.abort();};
  },[]);
  return ready;
}
