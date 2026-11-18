"""Differential legacy/Lua desktop gate inside a private hidden compositor.

The generated configs are real; startup commands are deliberately recorded or
replaced, never executed. Disposable GTK fixtures, private DBus/network/input,
no host profile, service, screen, keyboard or physical device changes.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shlex
import time
import subprocess
import sys

from hyprland_control import call, dispatch_args, rule_args, exec_args, uses_lua, config_path, guarded_layer, setting_args

spec = importlib.util.spec_from_file_location('private_driver', os.environ['MIGRATION_PRIVATE_DRIVER'])
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def option_value(name, text):
    try:
        value = json.loads(text)
    except ValueError:
        return text.strip()
    for key in ('int','bool','float','vec2','str','custom','css','gradient','font_weight'):
        if key in value:
            answer = value[key]
            # Legacy null strings are rendered with this sentinel.
            if answer == '[[EMPTY]]': answer = ''
            if name in ('group:groupbar:font_weight_active','group:groupbar:font_weight_inactive'):
                return int(answer)
            if isinstance(answer,str) and key in ('css','custom') and re.fullmatch(r'-?\d+(?:\.\d+)?(?: +-?\d+(?:\.\d+)?){0,3}',answer):
                nums = list(map(float,answer.split()))
                if len(nums) == 1: nums *= 4
                elif len(nums) == 2: nums *= 2
                elif len(nums) == 3: nums += nums[1:2]
                answer = nums
            return answer
    return value


def inner():
    root = Path(os.environ['TABLET_WINDOW_TEST_ROOT'])
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    assert root.parent == Path('/tmp') and root.name.startswith('twa.s.') and runtime == root/'r'
    assert not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    sys.path.insert(0,str(Path(os.environ['MIGRATION_SCREEN_SLEEP_SOURCE']).parent))
    power=driver.load('migration_screen_sleep',os.environ['MIGRATION_SCREEN_SLEEP_SOURCE'])
    processes = []
    snapshots = {}
    observations = {}
    def start(command,name):
        with (root/(name+'.log')).open('w') as log:
            process=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
        processes.append(process)
        return process
    def ctl(*args):
        return subprocess.check_output([os.environ['TABLET_TEST_HYPRCTL'],*args],text=True,timeout=5).strip()
    def mutate(*args):
        reply=ctl(*args)
        assert reply=='ok', (args,reply)
    def data(*args): return json.loads(ctl(*args,'-j'))
    def client(title): return next((c for c in data('clients') if c['title']==title),None)
    def evaluate(code): mutate('eval',code)
    def stop(p):
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
    try:
        (root/'labwc').mkdir()
        outer_process=start(['labwc','-C',str(root/'labwc')],'labwc')
        outer=driver.until(lambda:next((p for p in runtime.glob('wayland-*') if p.is_socket()),None),'outer')
        for backend in ('legacy','lua'):
            os.environ.pop('HYPRLAND_INSTANCE_SIGNATURE',None)
            os.environ['WAYLAND_DISPLAY']=outer.name
            config=root/('desktop.lua' if backend=='lua' else 'desktop.conf')
            if backend=='lua':
                text=Path(os.environ['MIGRATION_LUA_CONFIG']).read_text()
                text='desktop_test_startup={}\nhl.exec_cmd=function(command) table.insert(desktop_test_startup,command) end\n'+text
            else:
                text=Path(os.environ['MIGRATION_LEGACY_CONFIG']).read_text()
                text=re.sub(r'^exec-once=.*$', 'exec-once=true',text,flags=re.M)
            config.write_text(text)
            install=Path(os.environ['XDG_CONFIG_HOME'])/'hypr'
            install.mkdir(parents=True,exist_ok=True)
            entrypoint=install/('hyprland.lua' if backend=='lua' else 'hyprland.conf')
            entrypoint.unlink(missing_ok=True);entrypoint.symlink_to(config)
            compositor=start([os.environ['TABLET_TEST_HYPRLAND'],'-c',str(config)],backend)
            ipc=driver.until(lambda:next((runtime/'hypr').glob('*/.socket.sock'),None),'inner '+backend)
            os.environ['HYPRLAND_INSTANCE_SIGNATURE']=ipc.parent.name
            os.environ['WAYLAND_DISPLAY']=driver.until(lambda:next((p.name for p in runtime.glob('wayland-*') if p.is_socket() and p!=outer),None),'display')
            driver.until(lambda: ctl('configerrors')=='','valid '+backend)
            mutate('output','create','headless','eDP-1')
            driver.until(lambda:any(m['name']=='eDP-1' for m in data('monitors')),'panel')
            if backend=='lua':
                evaluate('assert(#desktop_test_startup==8)')
                observations['all_eight_real_startup_commands_intercepted_without_execution']=True
            descriptions=data('descriptions')
            names=[d['name'] for d in descriptions]
            values={}
            for offset in range(0,len(names),10):
                keys=names[offset:offset+10]
                result=ctl('--batch',';'.join('j/getoption '+name for name in keys)).split('\n\n\n')
                assert len(result)==len(keys),(len(result),keys)
                for name,value in zip(keys,result):
                    if backend=='lua' and value.strip()=='invalid type (internal error)':
                        # Pinned getoption does not recognize Lua font-weight's
                        # underlying type. Read the actual value via native API;
                        # never silently skip an unqueryable/default option.
                        assert name in ('group:groupbar:font_weight_active','group:groupbar:font_weight_inactive'),name
                        values[name]=int(ctl('repl','return hl.get_config('+json.dumps(name.replace(':','.'))+')'))
                        observations.setdefault('native_font_weight_getoption_gaps_read_via_get_config',[]).append(name)
                    else:
                        values[name]=option_value(name,value)
            binds=data('binds')
            # Native callbacks use internal Lua registry references instead of
            # legacy dispatcher/argument strings. The independent capture audit
            # verifies the exact dispatcher objects/arguments and command order.
            binds=[{k:v for k,v in b.items() if k not in ('dispatcher','arg')} for b in binds]
            snapshots[backend]={'options':values,'binds':binds,'animations':data('animations')}
            (root/(backend+'-snapshot.json')).write_text(json.dumps(snapshots[backend],indent=2))
            if backend=='lua':
                differences={k:[snapshots['legacy']['options'].get(k),v] for k,v in values.items() if snapshots['legacy']['options'].get(k)!=v}
                assert not differences, 'Effective option/default differences: '+json.dumps(differences,ensure_ascii=False)
                comparable_binds = [dict(b) for b in binds]
                # Native drag/resize dispatchers deliberately use __lua and
                # releasePending, not the legacy mouse dispatcher/flag. Keep
                # the raw snapshots and require actual drag/release tests too.
                for b in comparable_binds:
                    if b['modmask']==64 and b['key'] in ('mouse:272','mouse:273'):
                        assert b['mouse'] is False
                        b['mouse']=True
                assert snapshots['legacy']['binds']==comparable_binds, 'Effective binding flags/order differ; inspect snapshots'
                assert snapshots['legacy']['animations']==snapshots['lua']['animations'],'Effective animations differ'
                observations['all_reported_options_and_defaults_equal']=len(values)
                observations['effective_binding_flags_and_order_equal']=len(binds)
                observations['effective_animations_equal']=True
            if backend=='legacy':
                # Simulate HM activation while the legacy process is alive:
                # retain the exact old policy, install Lua beside it, then reload.
                pending=root/'pending.lua';pending.write_text(Path(os.environ['MIGRATION_LUA_CONFIG']).read_text())
                (install/'hyprland.lua').symlink_to(pending)
                transition=re.sub(r'^exec-once=.*$','exec-once=true',Path(os.environ['MIGRATION_TRANSITION_CONFIG']).read_text(),flags=re.M)
                config.write_text(transition)
                mutate('reload')
                assert not uses_lua() and config_path().resolve()==config
                assert len(data('binds'))==77 and guarded_layer('tablet-rotation-fade')
                assert [{k:v for k,v in b.items() if k not in ('dispatcher','arg')} for b in data('binds')]==binds
                assert ctl('configerrors')==''
                observations['legacy_reload_after_side_by_side_lua_activation_preserves_desktop']=True
            else:
                assert uses_lua() and config_path().resolve()==config
                assert guarded_layer('tablet-rotation-fade')
                swipe=data('getoption','gestures:workspace_swipe_touch')['bool']
                follow=data('getoption','input:follow_mouse')['int']
                mutate(*setting_args('gestures:workspace_swipe_touch',0));mutate(*setting_args('input:follow_mouse',0))
                assert data('getoption','gestures:workspace_swipe_touch')['bool'] is False
                assert data('getoption','input:follow_mouse')['int']==0
                mutate(*setting_args('gestures:workspace_swipe_touch',int(swipe)));mutate(*setting_args('input:follow_mouse',follow))
                observations['actual_lua_config_identity_guard_and_typed_interaction_restore']=True
            typed=subprocess.run([os.environ['MIGRATION_CONTROL'],'rule','migration-layout-cli',json.dumps({'match':{'title':'^Never mapped fixture$'},'float':True,'center':True,'size':'760 560'})],capture_output=True,text=True,timeout=10)
            assert typed.returncode==0 and typed.stdout.strip()=='ok',(backend,typed.stdout,typed.stderr)
            observations[backend+'_typed_rule_cli']=True
            # Equivalent geometry for window rule outcomes, independent of the
            # host's physical outputs. Do not execute the real startup helpers.
            typed_monitor=subprocess.run([os.environ['MIGRATION_CONTROL'],'monitor','--output','eDP-1','--mode','960x640@60','--position','0x0','--scale','1','--reset'],capture_output=True,text=True,timeout=10)
            assert typed_monitor.returncode==0 and typed_monitor.stdout.strip()=='ok',(backend,typed_monitor.stdout,typed_monitor.stderr)
            driver.until(lambda:any(m['width']==960 and m['scale']==1 for m in data('monitors')),'equivalent geometry')
            try:
                power.set_dpms('off')
                driver.until(lambda:any(m['name']=='eDP-1' and not m.get('dpmsStatus',True) for m in data('monitors')),'private DPMS off')
            finally:
                power.set_dpms('on')
            driver.until(lambda:any(m['name']=='eDP-1' and m.get('dpmsStatus',False) for m in data('monitors')),'private DPMS on')
            observations[backend+'_screen_sleep_dpms_transport_and_actual_state']=True
            fixtures=[]
            results={}
            for app,title in [('migration-layout','Display Layout'),('project-picker','Migration picker'),('slack','Migration Slack'),('spotify','Migration Spotify'),('teams-for-linux','Teams for Linux - auxiliary'),('pegasus-fe','Migration Pegasus')]:
                if backend=='lua':mutate(*dispatch_args('workspace','name:rule-baseline'))
                else:mutate('dispatch','workspace','name:rule-baseline')
                process=start([sys.executable,os.environ['MIGRATION_FIXTURE'],'--title',title,'--app-id',app],backend+'-'+app)
                fixtures.append(process)
                w=driver.until(lambda:client(title),'window '+title)
                # Wait out the configured entry animation before comparison.
                driver.until(lambda: (current:=client(title)) and current['size']==w['size'],'settled '+title)
                results[app]={k:w[k] for k in ('floating','pinned','fullscreen','workspace')}
                results[app]['workspace']=results[app]['workspace']['name']
                if app in ('migration-layout','project-picker'):
                    results[app]['size']=w['size']
            snapshots[backend]['rules']=results
            for p in reversed(fixtures):stop(p)
            def operation(name,argument):
                mutate(*(dispatch_args(name,argument) if backend=='lua' else ['dispatch',name,'--',argument]))
            operation('workspace','name:drag-test')
            drag_process=start([sys.executable,os.environ['MIGRATION_FIXTURE'],'--title','Private drag fixture','--app-id','migration-drag'],backend+'-drag')
            fixtures.append(drag_process)
            drag=driver.until(lambda:client('Private drag fixture'),'drag fixture')
            address='address:'+drag['address']
            operation('setfloating',address)
            operation('resizewindowpixel','exact 400 300,'+address)
            operation('movewindowpixel','exact 30 30,'+address)
            driver.until(lambda:client('Private drag fixture')['at']==[30,30],'initial drag geometry')
            pointer=subprocess.Popen([os.environ['TABLET_TEST_POINTER']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,start_new_session=True)
            processes.append(pointer)
            assert select.select([pointer.stdout],[],[],3)[0] and pointer.stdout.readline().strip()=='READY'
            def point(command):
                pointer.stdin.write(command+'\n');pointer.stdin.flush()
                assert select.select([pointer.stdout],[],[],3)[0] and pointer.stdout.readline().strip()=='OK'
            # wtype supplies synthetic keycodes in a tiny client keymap, not
            # physical GB keycodes. Use its symbols and no shared master ONLY
            # for this disposable device, equally on both backends, after the
            # full unmodified GB/shared-state policy snapshots were compared.
            if backend=='lua':
                evaluate(call('device',{'name':'hl-virtual-keyboard-wtype','share_states':0,'resolve_binds_by_sym':True}))
            else:
                mutate('keyword','device[hl-virtual-keyboard-wtype]:share_states','0')
                mutate('keyword','device[hl-virtual-keyboard-wtype]:resolve_binds_by_sym','true')
            modifier_marker=root/(backend+'-modifier-ready')
            if backend=='lua':
                evaluate('desktop_modifier_ready=false;hl.bind("SUPER + F12",function() desktop_modifier_ready=true end)')
            else:
                marker_command=shlex.join([sys.executable,'-c','from pathlib import Path;Path('+repr(str(modifier_marker))+').touch()'])
                mutate('keyword','bind','SUPER,F12,exec,'+marker_command)
            keyboard=start(['wtype','-s','200','-M','logo','-k','F12','-s','10000','-m','logo'],backend+'-keyboard')
            # wtype transmits a modifier mask, not a physical Super_L key.
            # A task-owned binding acknowledges that exact mask before motion.
            try:
                driver.until(lambda:ctl('repl','return desktop_modifier_ready')=='true' if backend=='lua' else modifier_marker.exists(),'private modifier mask acknowledged',timeout=5)
            except AssertionError:
                (root/(backend+'-input-diagnostics.json')).write_text(json.dumps({'devices':data('devices'),'binds':data('binds'),'focus':data('activewindow'),'keyboard_exit':keyboard.poll()},indent=2))
                raise
            point('move 180 180 960 640');point('down');point('move 280 230 960 640');point('up')
            moved=driver.until(lambda:(w:=client('Private drag fixture')) and w['at']!=[30,30] and w,'Super+left drag')
            at=moved['at']
            point('move 400 300 960 640')
            time.sleep(.1)
            assert client('Private drag fixture')['at']==at,'left-button release did not end drag'
            x=at[0]+moved['size'][0]-20;y=at[1]+moved['size'][1]-20
            point(f'move {x} {y} 960 640');point('right-down');point(f'move {x+50} {y+40} 960 640');point('right-up')
            resized=driver.until(lambda:(w:=client('Private drag fixture')) and w['size']!=moved['size'] and w,'Super+right resize')
            size=resized['size']
            point('move 200 200 960 640');time.sleep(.1)
            assert client('Private drag fixture')['size']==size,'right-button release did not end resize'
            snapshots[backend]['drag']={'delta':[at[0]-30,at[1]-30],'size_delta':[size[0]-moved['size'][0],size[1]-moved['size'][1]]}
            stop(pointer);stop(keyboard)
            operation('focuswindow',address)
            fullscreen_pairs=[]
            for requested in ('2 0','2 2','2 2','0 2','2 2','-1 0','2 -1'):
                operation('fullscreenstate',requested)
                state=client('Private drag fixture')
                fullscreen_pairs.append([state['fullscreen'],state['fullscreenClient']])
            snapshots[backend]['fullscreen_pairs']=fullscreen_pairs
            stop(drag_process)
            if backend=='lua':
                assert snapshots['legacy']['fullscreen_pairs']==fullscreen_pairs,('mixed fullscreen-state semantics differ',snapshots['legacy']['fullscreen_pairs'],fullscreen_pairs)
                observations['mixed_internal_client_fullscreen_pair_and_keep_current_semantics_equal']=True
                assert snapshots['legacy']['drag']==snapshots['lua']['drag'],('drag/resize delta differs',snapshots['legacy']['drag'],snapshots['lua']['drag'])
                observations['private_super_left_drag_and_right_resize_and_release_equivalent']=True
                assert snapshots['legacy']['rules']==results,('Rule outcomes differ',snapshots['legacy']['rules'],results)
                observations['representative_real_window_rule_outcomes_equal']=len(results)
                # One native object, bounded effects, including retired effects
                # disappearing from both its ordered vector and membership set.
                evaluate('desktop_rule=hl.window_rule({name="migration-bounded",enabled=false,match={class="^migration-bounded$"}})')
                for i in range(100):
                    code='local r=hl.window_rule({name="migration-bounded",enabled=false});assert(r==desktop_rule);assert(r:clear_effects()=='+str(0 if i==0 else 3)+');'
                    code+=call('window_rule',{'name':'migration-bounded','match':{'class':'^migration-bounded$'},'workspace':'name:bounded-'+str(i)+' silent','no_initial_focus':True,'suppress_event':'activate activatefocus'})
                    evaluate(code)
                rejected=subprocess.run([os.environ['TABLET_TEST_HYPRCTL'],'eval','desktop_rule:clear_effects()'],capture_output=True,text=True,timeout=5)
                assert 'disable the rule' in rejected.stdout
                mutate(*dispatch_args('workspace','name:human-baseline'))
                start([sys.executable,os.environ['MIGRATION_FIXTURE'],'--title','Bounded rule fixture','--app-id','migration-bounded'],'bounded')
                w=driver.until(lambda:client('Bounded rule fixture'),'bounded fixture')
                assert w['workspace']['name']=='bounded-99' and data('activeworkspace')['name']=='human-baseline'
                observations['one_native_rule_and_three_effects_after_100_updates']=True
                observations['enabled_rule_clear_refused_without_losing_placement_or_focus']=True
                # Native full reset versus partial update, with a second private
                # output to avoid ever entering a zero-output compositor state.
                mutate('output','create','headless','MIGRATION-DP')
                evaluate(call('monitor',{'output':'MIGRATION-DP','mode':'960x640@60','position':'auto-right','scale':1,'mirror':'eDP-1','reset':True}))
                driver.until(lambda:any(m['name']=='MIGRATION-DP' and m.get('mirrorOf','none')!='none' for m in data('monitors','all')),'mirror')
                evaluate(call('monitor',{'output':'MIGRATION-DP','mode':'960x640@60','position':'auto-right','scale':1,'reset':True}))
                driver.until(lambda:any(m['name']=='MIGRATION-DP' and m.get('mirrorOf','none')=='none' for m in data('monitors','all')),'unmirror')
                evaluate(call('monitor',{'output':'MIGRATION-DP','disabled':True,'reset':True}))
                driver.until(lambda:any(m['name']=='MIGRATION-DP' and m.get('disabled') for m in data('monitors','all')),'disabled')
                evaluate(call('monitor',{'output':'MIGRATION-DP','mode':'960x640@60','position':'auto-right','scale':1,'reset':True}))
                driver.until(lambda:any(m['name']=='MIGRATION-DP' and not m.get('disabled') for m in data('monitors','all')),'restored')
                before=next(m for m in data('monitors') if m['name']=='MIGRATION-DP')
                evaluate(call('monitor',{'output':'MIGRATION-DP','transform':1}))
                after=driver.until(lambda:next((m for m in data('monitors') if m['name']=='MIGRATION-DP' and m['transform']==1),None),'partial rotation')
                assert all(after[k]==before[k] for k in ('scale','width','height','x','y'))
                observations['mirror_extended_disable_restore_and_partial_rotation']=True
                # All primitive selectors/argument shapes used by owned callers
                # run against a real window, not mocked dispatcher strings.
                mutate(*dispatch_args('focuswindow','address:'+w['address']))
                for op,arg in [('setfloating','address:'+w['address']),('resizewindowpixel','exact 400 300,address:'+w['address']),('movewindowpixel','exact 20 30,address:'+w['address']),('setprop','address:'+w['address']+' sync_fullscreen 0'),('tagwindow','+migration-test address:'+w['address']),('tagwindow','-migration-test address:'+w['address']),('movetoworkspacesilent','name:primitive-target,address:'+w['address']),('focuswindow','address:'+w['address']),('fullscreenstate','2 2'),('fullscreenstate','0 0'),('settiled','address:'+w['address'])]:
                    mutate(*dispatch_args(op,arg))
                assert ctl('configerrors')==''
                observations['native_pixel_property_tag_workspace_and_fullscreen_adapters']=True
            # Exercise the actual comms script against existing disposable
            # application windows. Trap every launcher: no real app is opened
            # if a fixture fails to match or an existing-window path regresses.
            trapdir=root/'launch-traps';trapdir.mkdir(exist_ok=True)
            traplog=root/'unexpected-comms-launch'
            for name in ('slack','thunderbird','teams-for-linux'):
                trap=trapdir/name;trap.write_text('#!/bin/sh\nprintf unexpected >> '+shlex.quote(str(traplog))+'\nexit 99\n');trap.chmod(0o700)
            whatsapp=install/'scripts/zapzap-whatsapp';whatsapp.parent.mkdir(parents=True,exist_ok=True)
            whatsapp.write_text('#!/bin/sh\nprintf unexpected >> '+shlex.quote(str(traplog))+'\nexit 99\n');whatsapp.chmod(0o700)
            comms=[]
            for app,title in [('com.rtosta.zapzap','Comms WhatsApp'),('slack','Comms Slack'),('thunderbird','Comms Mail'),('teams-for-linux','Teams for Linux'),('teams-for-linux','Teams for Linux - auxiliary status')]:
                comms.append(start([sys.executable,os.environ['MIGRATION_FIXTURE'],'--title',title,'--app-id',app],backend+'-comms-'+str(len(comms))))
                driver.until(lambda:client(title),'comms fixture '+title)
            def run_comms():
                subprocess.run(['bash',os.environ['MIGRATION_COMMS_SCRIPT']],env={**os.environ,'PATH':str(trapdir)+':'+os.environ['PATH']},check=True,capture_output=True,text=True,timeout=30)
                assert not traplog.exists(),'Comms script tried to relaunch an existing application'
            run_comms()
            titles=('Comms WhatsApp','Comms Slack','Comms Mail','Teams for Linux')
            members={client(title)['address'] for title in titles}
            driver.until(lambda:all(members <= set(client(title).get('grouped',[])) for title in titles),'four real comms windows grouped')
            assert not client('Teams for Linux - auxiliary status')['grouped'],'auxiliary Teams window was swallowed'
            assert all(not client(title)['floating'] for title in titles)
            operation('focuswindow','address:'+client('Comms Slack')['address'])
            run_comms()
            assert data('activewindow')['title']=='Comms Slack','Comms reentry lost the selected tab'
            observations[backend+'_real_comms_group_and_auxiliary_exclusion_and_tab_preserving_reentry']=True
            for p in reversed(comms):stop(p)
            project=Path(os.environ['MIGRATION_PROJECT_PACKAGE'])
            operation('workspace','name:picker-first')
            picker=start([str(project/'bin/project-picker-gui'),'--daemon','--show'],backend+'-actual-picker')
            def picker_window():
                return next((w for w in data('clients') if w['pid']==picker.pid and w['class'] in ('dev.project_object.Picker','project-picker')),None)
            shown=driver.until(picker_window,'actual picker shown')
            assert shown['workspace']['name']=='picker-first' and shown['floating'] and shown['pinned']
            subprocess.run([str(project/'bin/project-picker')],check=True,timeout=10)
            driver.until(lambda:not picker_window(),'actual picker dismiss')
            assert picker.poll() is None,'dismiss killed the persistent picker'
            operation('workspace','name:picker-second')
            subprocess.run([str(project/'bin/project-picker')],check=True,timeout=10)
            shown=driver.until(lambda:(w:=picker_window()) and w['workspace']['name']=='picker-second' and w,'actual picker moved and shown')
            observations[backend+'_real_persistent_picker_show_dismiss_and_move']=True
            stop(picker)
            (root/(backend+'-snapshot.json')).write_text(json.dumps(snapshots[backend],indent=2))
            for p in reversed(fixtures):stop(p)
            stop(compositor)
            driver.until(lambda:not ipc.exists(),'compositor stopped')
            os.environ.pop('HYPRLAND_INSTANCE_SIGNATURE',None)
        (root/'observations.json').write_text(json.dumps(observations,indent=2))
        print(json.dumps(observations,indent=2),flush=True)
        print('PASS: isolated desktop differential/native lifecycle gate. No physical/live acceptance claimed.',flush=True)
        return 0
    finally:
        for p in reversed(processes):stop(p)
        driver.load('cleanup',os.environ['TABLET_TEST_CLEANUP']).cleanup_runtime(runtime)


if __name__=='__main__':
    raise SystemExit(inner() if os.environ.get('TABLET_WINDOW_TEST_ROOT') else driver.outer(__file__))
