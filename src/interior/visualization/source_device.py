"""Per-process Cycles device selection; source scene files are never saved."""
import bpy


def configure(scene):
    preferences=bpy.context.preferences.addons['cycles'].preferences
    failures=[];devices=[];backend='CPU'
    for candidate in ('OPTIX','CUDA','HIP','METAL','ONEAPI'):
        try:
            preferences.compute_device_type=candidate;preferences.get_devices()
            devices=[d for d in preferences.devices if d.type==candidate]
            if devices:backend=candidate;break
        except (TypeError,ValueError,RuntimeError) as error:failures.append(dict(backend=candidate,reason=str(error)))
    for device in preferences.devices:device.use=backend!='CPU' and device.type==backend
    scene.render.engine='CYCLES';scene.cycles.device='CPU' if backend=='CPU' else 'GPU'
    scene.cycles.use_denoising=True;scene.cycles.denoiser='OPTIX' if backend=='OPTIX' else 'OPENIMAGEDENOISE'
    scene.cycles.denoising_use_gpu=backend!='CPU';scene.cycles.use_adaptive_sampling=True
    scene.cycles.adaptive_threshold=.04;scene.cycles.seed=1020;scene.cycles.use_animated_seed=False
    return dict(blender=bpy.app.version_string,requested_backend=backend,requested_denoiser=scene.cycles.denoiser,
                selected_devices=[dict(name=d.name,type=d.type) for d in devices],
                cpu_fallback=backend=='CPU',probe_failures=failures,
                note='No compatible GPU found; CPU selected explicitly' if backend=='CPU' else 'Actual execution evidence is retained in the Cycles debug log')
