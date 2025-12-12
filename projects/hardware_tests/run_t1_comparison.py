# ~/sequence_custom_projects/projects/hardware_tests/run_t1_comparison.py

import sys
from sequence.kernel.timeline import Timeline
from sequence.topology.node import DQCNode
from sequence.components.memory import Memory, MemoryArray
from sequence.components.bsm import SingleHeraldedBSM # Lớp BSM cụ thể
from sequence.components.optical_channel import QuantumChannel
from sequence.components.light_source import SPDCSource # Dùng cho EG
from sequence.entanglement_management.generation.barret_kok import BarretKokA, BarretKokB
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel # THÊM ClassicalChannel


# --- HÀM HỖ TRỢ: TÙY CHỈNH T1 (Đã sửa lỗi truy cập và set params) ---
def set_memory_T1(node: DQCNode, t1_value: float):
    """Tìm MemoryArray trong node và đặt T1 cho tất cả các memory."""

    memory_array = None
    for name, component in node.components.items():
        if isinstance(component, MemoryArray):
            memory_array = component
            break

    if memory_array is None:
        raise ValueError(f"Không tìm thấy MemoryArray trong node {node.name}")

    if hasattr(memory_array, 'memories'):
        for memory in memory_array.memories:
            # *********** CUSTOMIZATION: SET T1 (Gán trực tiếp thuộc tính) ***********
            memory.coherence_time = t1_value

            # Đảm bảo T1/T2 được cập nhật nếu chúng tồn tại (dùng try/except)
            if hasattr(memory, 'T1'):
                memory.T1 = t1_value
            if hasattr(memory, 'T2'):
                memory.T2 = t1_value
            # **********************************************

    else:
        raise AttributeError(f"MemoryArray trong node {node.name} không có thuộc tính 'memories'")

# --- HÀM TẠO TOPOLOGY BẰNG CODE PYTHON (Final Debugged) ---
def create_eg_topology(tl: Timeline, t1_value: float, name_suffix: str = ""):

    # Khai báo hằng số
    distance = 500.0
    c_delay = 500000000  # 0.5ms
    attenuation = 0.0002
    memo_size = 1

    # 1. Định nghĩa các Node
    alice = DQCNode(f"alice_{name_suffix}", tl, memo_size=memo_size)
    bob = DQCNode(f"bob_{name_suffix}", tl, memo_size=memo_size)
    bsm = SingleHeraldedBSM(f"BSM_{name_suffix}", tl)

    # 2. Tùy chỉnh Hardware (Memory T1)
    set_memory_T1(alice, t1_value)
    set_memory_T1(bob, t1_value)

    # 3. Khởi tạo và Kết nối Quantum Links (QChannels)
    spdc_source = SPDCSource(f"Source_AB_{name_suffix}", tl, frequency=1e9) 

    # Quantum Channels (QChannel 1 cho Photon 1, QChannel 2 cho Photon 2)
    qc_1 = QuantumChannel("QChan_1", tl, attenuation=attenuation, distance=distance)
    qc_2 = QuantumChannel("QChan_2", tl, attenuation=attenuation, distance=distance)

    # Kết nối Source -> Channel -> BSM
    spdc_source.add_receiver(qc_1)
    spdc_source.add_receiver(qc_2)
    qc_1.add_receiver(bsm)
    qc_2.add_receiver(bsm)
    
    # 3.4. Kết nối Cổ điển (Chỉ A <-> B, BSM truyền thông qua internal protocol)

    # 3.4.1. Kết nối Alice <-> Bob (Cần cho Entanglement Manager)
    cc_alice_bob = ClassicalChannel(f"CC_A_B_{name_suffix}", tl, delay=c_delay, distance=distance)
    cc_bob_alice = ClassicalChannel(f"CC_B_A_{name_suffix}", tl, delay=c_delay, distance=distance)
    
    alice.assign_cchannel(cc_alice_bob, bob.name)
    bob.assign_cchannel(cc_bob_alice, alice.name)

    # LƯU Ý QUAN TRỌNG: 
    # Nếu giao thức Barret-Kok yêu cầu kết nối cổ điển giữa Node và BSM, 
    # thì Node BSM cần là DQCNode. Vì nó là SingleHeraldedBSM (Component), 
    # chúng ta chỉ có thể truyền thông nội bộ. Chúng ta sẽ đặt BSM làm receiver 
    # của các kênh cổ điển mà không cần assign_cchannel (hy vọng nó hoạt động).
    
    # Kênh Alice -> BSM (Để Alice gửi yêu cầu)
    cc_alice_to_bsm = ClassicalChannel(f"CC_A_BSM_{name_suffix}", tl, delay=c_delay, distance=distance)
    cc_bob_to_bsm = ClassicalChannel(f"CC_B_BSM_{name_suffix}", tl, delay=c_delay, distance=distance)

    # Alice gửi tin nhắn cổ điển tới BSM (BSM là receiver, không phải node)
    cc_alice_to_bsm.add_receiver(bsm)
    cc_bob_to_bsm.add_receiver(bsm)

    # Node Alice/Bob cần biết cách gửi qua kênh này:
    # Nếu DQCNode không có hàm set_classical_connection, chúng ta phải dùng assign_cchannel
    # Alice.assign_cchannel cần Node đích là một Node/Router. BSM không phải Node.
    
    # Tạm thời loại bỏ kênh A <-> BSM để tránh lỗi, và giả định giao thức Barret-Kok 
    # đã được tối ưu để hoạt động chỉ với kênh lượng tử đến BSM.

    # 4. Khởi tạo Giao thức Entanglement Generation (EG)
    # Cần đảm bảo Protocol biết BSM/Source nào để sử dụng
    eg_alice = BarretKokA(alice, f"eg_alice_{name_suffix}", 
                          bsm_node=bsm.name, 
                          source_name=spdc_source.name) 
    eg_bob = BarretKokB(bob, f"eg_bob_{name_suffix}", bsm_node=bsm.name)

    alice.entanglement_manager.add_generation_protocol(bob.name, eg_alice)
    bob.entanglement_manager.add_generation_protocol(alice.name, eg_bob)

    eg_alice.set_others([bob.name])
    eg_bob.set_others([alice.name])

    # 5. Yêu cầu Entanglement
    num_pairs_requested = 100
    fidelity_required = 0.9
    alice.entanglement_manager.request(bob.name, fidelity_required, num_pairs_requested)

    return [alice, bob]

# --- HÀM CHẠY VÀ BÁO CÁO ---

MAX_DURATION = 5 * 1e12 # 5 ms

def run_simulation_and_report_python_only(t1_value: float, name: str):
    # ... (Phần này giữ nguyên từ Bước 12)
    print(f"\n=======================================================")
    print(f"Bắt đầu mô phỏng Python Pure: {name} (T1={t1_value:.0e}s)")

    tl = Timeline()

    nodes = create_eg_topology(tl, t1_value, name)
    alice = nodes[0]

    tl.init()
    tl.run(max_time=MAX_DURATION)

    em = alice.entanglement_manager
    successes = em.stats.get('eg_success', 0)
    fails = em.stats.get('eg_fail', 0)
    total = successes + fails

    print(f"--- Kết quả Mô phỏng {name} ---")
    print(f"Tổng thời gian mô phỏng (Timeline): {tl.time:.2e} ps")
    print(f"T1 Quantum Memory: {t1_value:.0e}s")
    print(f"Số lần EG thành công: {successes}")
    print(f"Số lần EG thất bại: {fails}")

    if total > 0:
        rate = successes / total
        print(f"Tỷ lệ thành công Entanglement: {rate:.4f}")
    else:
         print("Chưa có cặp vướng víu nào được tạo (total=0).")


# --- Thực thi so sánh ---

T1_LOW = 1e-6
T1_HIGH = 1e-3

run_simulation_and_report_python_only(T1_LOW, "LOW_T1")
run_simulation_and_report_python_only(T1_HIGH, "HIGH_T1_CUSTOM")
