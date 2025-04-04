"""
Módulo Híbrido Unificado de Integración Neuronal Cuántico-Clásico

Este módulo combina las funcionalidades de init_activation.py e inicializador.py para
definir un sistema completo que integra:
  • Una red neural clásica (NeuralNetwork) con múltiples funciones de activación y
    soporte para optimizadores (SGD y Adam).
  • Un activador cuántico-clásico (QuantumClassicalActivator) que crea circuitos cuánticos
    relacionados con funciones de activación y permite realizar un paso forward híbrido.
  • Un sistema de estado cuántico (QuantumState) que utiliza métodos bayesianos y distancias
    de Mahalanobis para gestionar y predecir estados cuánticos (incorporando las funcionalidades
    más completas de init_activation.py).

Autor: Jacobo Tlacaelel Mina Rodríguez
Fecha: 29/03/2025
Versión: cuadrante-coremind v1.5 (Combinación de v1.0 y v1.0)
"""

import numpy as np
import tensorflow as tf
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit.circuit import Parameter
from typing import Tuple, List, Optional, Dict, Union, Any
from enum import Enum
import joblib
import tensorflow_probability as tfp
from scipy.spatial.distance import mahalanobis
from sklearn.covariance import EmpiricalCovariance
# Se asume que bayes_logic.py está en el mismo directorio
from bayes_logic import BayesLogic
from statistical_analysis import StatisticalAnalysis  # Asumiendo que StatisticalAnalysis está en su propio archivo

class QuantumBayesMahalanobis(BayesLogic):
    """
    Clase que combina la lógica de Bayes con el cálculo de la distancia de Mahalanobis
    aplicada a estados cuánticos, permitiendo proyecciones vectorizadas e inferencias
    de coherencia/entropía.
    """
    def __init__(self):
        """
        Constructor que inicializa el estimador de covarianza para su posterior uso.
        """
        super().__init__()
        self.covariance_estimator = EmpiricalCovariance()

    def _get_inverse_covariance(self, data: np.ndarray) -> np.ndarray:
        """
        Ajusta el estimador de covarianza con los datos y retorna la inversa de la
        matriz de covarianza. Si la matriz no fuera invertible, se retorna la
        pseudo-inversa (pinv).

        Parámetros:
        -----------
        data: np.ndarray
            Datos con forma (n_muestras, n_dimensiones).

        Retorna:
        --------
        inv_cov_matrix: np.ndarray
            Inversa o pseudo-inversa de la matriz de covarianza estimada.
        """
        if data.ndim != 2:
            raise ValueError("Los datos deben ser una matriz bidimensional (n_muestras, n_dimensiones).")
        self.covariance_estimator.fit(data)
        cov_matrix = self.covariance_estimator.covariance_
        try:
            inv_cov_matrix = np.linalg.inv(cov_matrix)
        except np.linalg.LinAlgError:
            inv_cov_matrix = np.linalg.pinv(cov_matrix)
        return inv_cov_matrix

    def compute_quantum_mahalanobis(self,
                                    quantum_states_A: np.ndarray,
                                    quantum_states_B: np.ndarray) -> np.ndarray:
        """
        Calcula la distancia de Mahalanobis para cada estado en 'quantum_states_B'
        respecto a la distribución de 'quantum_states_A'. Retorna un arreglo 1D
        con tantas distancias como filas tenga 'quantum_states_B'.

        Parámetros:
        -----------
        quantum_states_A: np.ndarray
            Representa el conjunto de estados cuánticos de referencia.
            Forma esperada: (n_muestras, n_dimensiones).

        quantum_states_B: np.ndarray
            Estados cuánticos para los que calcularemos la distancia
            de Mahalanobis. Forma: (n_muestras, n_dimensiones).

        Retorna:
        --------
        distances: np.ndarray
            Distancias de Mahalanobis calculadas para cada entrada de B.
        """
        if quantum_states_A.ndim != 2 or quantum_states_B.ndim != 2:
            raise ValueError("Los estados cuánticos deben ser matrices bidimensionales.")
        if quantum_states_A.shape[1] != quantum_states_B.shape[1]:
            raise ValueError("La dimensión (n_dimensiones) de A y B debe coincidir.")

        inv_cov_matrix = self._get_inverse_covariance(quantum_states_A)
        mean_A = np.mean(quantum_states_A, axis=0)

        diff_B = quantum_states_B - mean_A  # (n_samples_B, n_dims)
        aux = diff_B @ inv_cov_matrix       # (n_samples_B, n_dims)
        dist_sqr = np.einsum('ij,ij->i', aux, diff_B)  # Producto elemento a elemento y sumatoria por fila
        distances = np.sqrt(dist_sqr)
        return distances

    def quantum_cosine_projection(self,
                                  quantum_states: np.ndarray,
                                  entropy: float,
                                  coherence: float) -> tf.Tensor:
        """
        Proyecta los estados cuánticos usando cosenos directores y calcula la
        distancia de Mahalanobis entre dos proyecciones vectorizadas (A y B).
        Finalmente retorna las distancias normalizadas (softmax).

        Parámetros:
        -----------
        quantum_states: np.ndarray
            Estados cuánticos de entrada con forma (n_muestras, 2).
        entropy: float
            Entropía del sistema a usar en la función calculate_cosines.
        coherence: float
            Coherencia del sistema a usar en la función calculate_cosines.

        Retorna:
        --------
        normalized_distances: tf.Tensor
            Tensor 1D con las distancias normalizadas (softmax).
        """
        if quantum_states.shape[1] != 2:
            raise ValueError("Se espera que 'quantum_states' tenga exactamente 2 columnas.")
        cos_x, cos_y, cos_z = StatisticalAnalysis.calculate_cosines(entropy, coherence)

        # Proyección A: multiplicar cada columna por (cos_x, cos_y)
        projected_states_A = quantum_states * np.array([cos_x, cos_y])
        # Proyección B: multiplicar cada columna por (cos_x*cos_z, cos_y*cos_z)
        projected_states_B = quantum_states * np.array([cos_x * cos_z, cos_y * cos_z])

        # Calcular distancias de Mahalanobis vectorizadas
        mahalanobis_distances = self.compute_quantum_mahalanobis(
            projected_states_A,
            projected_states_B
        )

        # Convertir a tensor y normalizar con softmax
        mahalanobis_distances_tf = tf.convert_to_tensor(mahalanobis_distances, dtype=tf.float32)
        normalized_distances = tf.nn.softmax(mahalanobis_distances_tf)
        return normalized_distances

    def calculate_quantum_posterior_with_mahalanobis(self,
                                                     quantum_states: np.ndarray,
                                                     entropy: float,
                                                     coherence: float):
        """
        Calcula la probabilidad posterior usando la distancia de Mahalanobis
        en proyecciones cuánticas e integra la lógica de Bayes.

        Parámetros:
        -----------
        quantum_states: np.ndarray
            Matriz de estados cuánticos (n_muestras, 2).
        entropy: float
            Entropía del sistema.
        coherence: float
            Coherencia del sistema.

        Retorna:
        --------
        posterior: tf.Tensor
            Probabilidad posterior calculada combinando la lógica bayesiana.
        quantum_projections: tf.Tensor
            Proyecciones cuánticas normalizadas (distancias softmax).
        """
        quantum_projections = self.quantum_cosine_projection(
            quantum_states,
            entropy,
            coherence
        )

        # Calcular covarianza en las proyecciones
        tensor_projections = tf.convert_to_tensor(quantum_projections, dtype=tf.float32)
        quantum_covariance = tfp.stats.covariance(tensor_projections, sample_axis=0)

        # Calcular prior cuántico basado en la traza de la covarianza
        dim = tf.cast(tf.shape(quantum_covariance)[0], tf.float32)
        quantum_prior = tf.linalg.trace(quantum_covariance) / dim

        # Calcular otros componentes para la posteriori (usando métodos heredados de BayesLogic).
        prior_coherence = self.calculate_high_coherence_prior(coherence)
        joint_prob = self.calculate_joint_probability(
            coherence,
            1,  # variable arbitraria: "evento" = 1
            tf.reduce_mean(tensor_projections)
        )
        cond_prob = self.calculate_conditional_probability(joint_prob, quantum_prior)
        posterior = self.calculate_posterior_probability(quantum_prior,
                                                         prior_coherence,
                                                         cond_prob)
        return posterior, quantum_projections

    def predict_quantum_state(self,
                              quantum_states: np.ndarray,
                              entropy: float,
                              coherence: float):
        """
        Predice el siguiente estado cuántico con base en la proyección y la distancia
        de Mahalanobis, generando un "estado futuro".

        Parámetros:
        -----------
        quantum_states: np.ndarray
            Estados cuánticos de entrada (n_muestras, 2).
        entropy: float
            Entropía del sistema.
        coherence: float
            Coherencia del sistema.

        Retorna:
        --------
        next_state_prediction: tf.Tensor
            Predicción del siguiente estado cuántico.
        posterior: tf.Tensor
            Probabilidad posterior que se usó en la predicción.
        """
        posterior, projections = self.calculate_quantum_posterior_with_mahalanobis(
            quantum_states,
            entropy,
            coherence
        )

        # Generar un estado futuro ponderado por la posterior
        # Posterior es escalar, mientras que projections es un vector
        next_state_prediction = tf.reduce_sum(
            tf.multiply(projections, tf.expand_dims(posterior, -1)),
            axis=0
        )
        return next_state_prediction, posterior


class EnhancedPRN(BayesLogic): # Hereda de BayesLogic como en init_activation
    """
    Extiende la clase PRN para registrar distancias de Mahalanobis y con ello
    definir un 'ruido cuántico' adicional en el sistema.
    """
    def __init__(self, influence: float = 0.5, algorithm_type: str = None, **parameters):
        """
        Constructor que permite definir la influencia y el tipo de algoritmo,
        además de inicializar una lista para conservar registros promedio de
        distancias de Mahalanobis.
        """
        super().__init__() # Llama al constructor de BayesLogic
        self.influence = influence
        self.algorithm_type = algorithm_type
        self.parameters = parameters
        self.prn_records = []
        self.mahalanobis_records = []

    def record_noise(self, probabilities: dict) -> float:
        """
        Calcula y registra la entropía de Shannon basada en las probabilidades.

        Parámetros:
        -----------
        probabilities: dict
            Diccionario de probabilidades (ej. {"0": p_0, "1": p_1, ...}).

        Retorna:
        --------
        entropy: float
            Entropía calculada.
        """
        probs = np.array(list(probabilities.values()))
        probs = probs[probs > 0]
        entropy = -np.sum(probs * np.log2(probs))
        self.prn_records.append(entropy)
        return entropy

    def record_quantum_noise(self, probabilities: dict, quantum_states: np.ndarray):
        """
        Registra un 'ruido cuántico' basado en la distancia de Mahalanobis
        calculada para los estados cuánticos.

        Parámetros:
        -----------
        probabilities: dict
            Diccionario de probabilidades (ej. {"0": p_0, "1": p_1, ...}).
        quantum_states: np.ndarray
            Estados cuánticos (n_muestras, n_dimensiones).

        Retorna:
        --------
        (entropy, mahal_mean): Tuple[float, float]
            - Entropía calculada a partir de probabilities.
            - Distancia promedio de Mahalanobis.
        """
        # Calculamos la entropía
        entropy = self.record_noise(probabilities)

        # Ajuste del estimador de covarianza
        cov_estimator = EmpiricalCovariance().fit(quantum_states)
        mean_state = np.mean(quantum_states, axis=0)
        inv_cov = np.linalg.pinv(cov_estimator.covariance_)

        # Cálculo vectorizado de la distancia
        diff = quantum_states - mean_state
        aux = diff @ inv_cov
        dist_sqr = np.einsum('ij,ij->i', aux, diff)
        distances = np.sqrt(dist_sqr)
        mahal_mean = np.mean(distances)

        # Se registra la distancia promedio
        self.mahalanobis_records.append(mahal_mean)

        return entropy, mahal_mean


class QuantumNoiseCollapse(QuantumBayesMahalanobis):
    """
    Combina la lógica bayesiana cuántica (QuantumBayesMahalanobis) y el registro EnhancedPRN
    para simular el 'colapso de onda' usando distancias de Mahalanobis como parte del ruido.
    """
    def __init__(self, prn_influence: float = 0.5):
        """
        Constructor que crea internamente un EnhancedPRN por defecto, con una
        influencia configurable.
        """
        super().__init__()
        self.prn = EnhancedPRN(influence=prn_influence)

    def simulate_wave_collapse(self,
                               quantum_states: np.ndarray,
                               prn_influence: float,
                               previous_action: int):
        """
        Simula el colapso de onda incorporando ruido cuántico (a través de PRN) e
        integra el resultado para determinar una acción bayesiana.

        Parámetros:
        -----------
        quantum_states: np.ndarray
            Estados cuánticos de entrada.
        prn_influence: float
            Influencia del PRN en el sistema (se puede alinear con self.prn.influence).
        previous_action: int
            Acción previa del sistema que se utiliza como condicionante.

        Retorna:
        --------
        dict con llaves:
            "collapsed_state": tf.Tensor
                Representación final colapsada del estado.
            "action": int
                Acción tomada según lógica bayesiana.
            "entropy": float
                Entropía calculada.
            "coherence": float
                Coherencia derivada.
            "mahalanobis_distance": float
                Distancia promedio de Mahalanobis.
            "cosines": Tuple[float, float, float]
                Valores de (cos_x, cos_y, cos_z) usados en la proyección.
        """
        # Diccionario de probabilidades a modo de ejemplo
        probabilities = {str(i): np.sum(state) for i, state in enumerate(quantum_states)}

        # Registro de entropía y distancia de Mahalanobis
        entropy, mahalanobis_mean = self.prn.record_quantum_noise(probabilities, quantum_states)

        # Cálculo de los cosenos directores como ejemplo de proyección
        cos_x, cos_y, cos_z = StatisticalAnalysis.calculate_cosines(entropy, mahalanobis_mean)

        # Definimos coherencia a partir de la distancia de Mahalanobis y los cosenos
        coherence = np.exp(-mahalanobis_mean) * (cos_x + cos_y + cos_z) / 3.0

        # Llamada a un método de BayesLogic para decidir la acción
        bayes_probs = self.calculate_probabilities_and_select_action(
            entropy=entropy,
            coherence=coherence,
            prn_influence=prn_influence,
            action=previous_action
        )

        # Proyectar estados cuánticos
        projected_states = self.quantum_cosine_projection(
            quantum_states,
            entropy,
            coherence
        )

        # Ejemplo de 'colapso' multiplicando la proyección por la acción que se toma
        collapsed_state = tf.reduce_sum(
            tf.multiply(
                projected_states,
                tf.cast(bayes_probs["action_to_take"], tf.float32)
            )
        )

        return {
            "collapsed_state": collapsed_state,
            "action": bayes_probs["action_to_take"],
            "entropy": entropy,
            "coherence": coherence,
            "mahalanobis_distance": mahalanobis_mean,
            "cosines": (cos_x, cos_y, cos_z)
        }

    def objective_function_with_noise(self,
                                      quantum_states: np.ndarray,
                                      target_state: np.ndarray,
                                      entropy_weight: float = 1.0) -> tf.Tensor:
        """
        Función objetivo que combina fidelidad, entropía y distancia de Mahalanobis
        para encontrar un compromiso entre mantener la fidelidad al estado objetivo
        y el ruido cuántico en el sistema.

        Parámetros:
        -----------
        quantum_states: np.ndarray
            Estados cuánticos actuales (n_muestras, n_dimensiones).
        target_state: np.ndarray
            Estado objetivo que se desea alcanzar.
        entropy_weight: float
            Factor que pondera la influencia de la entropía en la función objetivo.

        Retorna:
        --------
        objective_value: tf.Tensor
            Valor de la función objetivo (cuanto menor, mejor).
        """
        # Calcular fidelidad (simple ejemplo): |<ψ|φ>|^2
        # Suponiendo que (quantum_states y target_state) sean vectores compatibles
        fidelity = tf.abs(tf.reduce_sum(quantum_states * tf.cast(target_state, quantum_states.dtype)))**2

        # Registrar 'ruido': entropía y distancia de Mahalanobis
        probabilities = {str(i): np.sum(st) for i, st in enumerate(quantum_states)}
        entropy, mahalanobis_dist = self.prn.record_quantum_noise(probabilities, quantum_states)

        # Combinar métricas: (1 - fidelidad) + factor * entropía + penalización por distancia
        objective_value = ((1.0 - fidelity)
                           + entropy_weight * entropy
                           + (1.0 - np.exp(-mahalanobis_dist)))

        return objective_value

    def optimize_quantum_state(self,
                               initial_states: np.ndarray,
                               target_state: np.ndarray,
                               max_iterations: int = 100,
                               learning_rate: float = 0.01):
        """
        Optimiza los estados cuánticos para acercarlos al estado objetivo,
        mediante un descenso de gradiente (Adam).

        Parámetros:
        -----------
        initial_states: np.ndarray
            Estados cuánticos iniciales.
        target_state: np.ndarray
            Estado objetivo.
        max_iterations: int
            Número máximo de iteraciones de optimización.
        learning_rate: float
            Tasa de aprendizaje para Adam.

        Retorna:
        --------
        best_states: np.ndarray
            Estados optimizados que reportan el menor valor de la función objetivo.
        best_objective: float
            Valor final alcanzado por la función objetivo.
        """
        # Convertir a tf.Variable para permitir gradientes
        current_states = tf.Variable(initial_states, dtype=tf.float32)

        best_objective = float('inf')
        best_states = current_states.numpy().copy()

        optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate)

        for _ in range(max_iterations):
            with tf.GradientTape() as tape:
                # Usar numpy() en la llamada para separar lógicamente la parte TF de la parte numpy
                objective = self.objective_function_with_noise(current_states.numpy(), target_state)
            grads = tape.gradient(objective, [current_states])

            if grads[0] is None:
                # Si no hay gradiente, rompe el bucle
                break

            optimizer.apply_gradients(zip(grads, [current_states]))

            # Re-evaluar después de actualizar los parámetros
            new_objective = self.objective_function_with_noise(current_states.numpy(), target_state)
            if new_objective < best_objective:
                best_objective = new_objective
                best_states = current_states.numpy().copy()

        return best_states, best_objective


# -------------------------
# Funciones de activación clásicas (redefinidas aquí para el módulo unificado)
# -------------------------
def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))

def sigmoid_derivative(x: np.ndarray) -> np.ndarray:
    return x * (1 - x)

def tanh(x: np.ndarray) -> np.ndarray:
    return np.tanh(x)

def tanh_derivative(x: np.ndarray) -> np.ndarray:
    return 1 - np.tanh(x)**2

def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0, x)

def relu_derivative(x: np.ndarray) -> np.ndarray:
    return np.where(x > 0, 1, 0)

# -------------------------
# Red neuronal clásica (redefinida aquí para el módulo unificado)
# -------------------------
class NeuralNetwork:
    def __init__(self, input_size: int, hidden_size: list[int], output_size: int, activation: str = "sigmoid"):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.activation = activation
        self.weights = []
        self.biases = []

        previous_size = input_size
        for hs in hidden_size:
            self.weights.append(np.random.randn(previous_size, hs))
            self.biases.append(np.zeros((1, hs)))
            previous_size = hs
        self.weights.append(np.random.randn(previous_size, output_size))
        self.biases.append(np.zeros((1, output_size)))

    def activate(self, x: np.ndarray) -> np.ndarray:
        if self.activation == "sigmoid":
            return sigmoid(x)
        elif self.activation == "tanh":
            return tanh(x)
        elif self.activation == "relu":
            return relu(x)
        else:
            raise ValueError("Función de activación no reconocida.")

    def activate_derivative(self, x: np.ndarray) -> np.ndarray:
        if self.activation == "sigmoid":
            return sigmoid_derivative(x)
        elif self.activation == "tanh":
            return tanh_derivative(x)
        elif self.activation == "relu":
            return relu_derivative(x)
        else:
            raise ValueError("Función de activación no reconocida.")

    def forward(self, X: np.ndarray) -> list[np.ndarray]:
        activations = [X]
        for w, b in zip(self.weights, self.biases):
            X = self.activate(np.dot(X, w) + b)
            activations.append(X)
        return activations

    def backward(self, X: np.ndarray, y: np.ndarray, learning_rate: float = 0.1, optimizer: str = "sgd", **kwargs):
        activations = self.forward(X)
        output = activations[-1]
        output_error = y - output
        deltas = [output_error * self.activate_derivative(activations[-1])]
        for i in reversed(range(len(self.weights) - 1)):
            delta = deltas[-1].dot(self.weights[i + 1].T) * self.activate_derivative(activations[i + 1])
            deltas.append(delta)
        deltas.reverse()
        for i in range(len(self.weights)):
            if optimizer == "sgd":
                self.weights[i] += activations[i].T.dot(deltas[i]) * learning_rate
                self.biases[i] += np.sum(deltas[i], axis=0, keepdims=True) * learning_rate
            elif optimizer == "adam":
                self._adam(i, activations[i], deltas[i], learning_rate, **kwargs)
            else:
                raise ValueError("Optimizador no reconocido.")

    def _adam(self, layer: int, a: np.ndarray, delta: np.ndarray, learning_rate: float, t: int = 1,
              beta1=0.9, beta2=0.999, epsilon=1e-8, m_w=None, v_w=None, m_b=None, v_b=None):
        if not hasattr(self, 'm_w'):
            self.m_w = [np.zeros_like(w) for w in self.weights]
            self.v_w = [np.zeros_like(w) for w in self.weights]
            self.m_b = [np.zeros_like(b) for b in self.biases]
            self.v_b = [np.zeros_like(b) for b in self.biases]

        self.m_w[layer] = beta1 * self.m_w[layer] + (1 - beta1) * a.T.dot(delta)
        self.v_w[layer] = beta2 * self.v_w[layer] + (1 - beta2) * np.square(a.T.dot(delta))
        m_hat_w = self.m_w[layer] / (1 - beta1**t)
        v_hat_w = self.v_w[layer] / (1 - beta2**t)
        self.weights[layer] += learning_rate * m_hat_w / (np.sqrt(v_hat_w) + epsilon)
        self.m_b[layer] = beta1 * self.m_b[layer] + (1 - beta1) * np.sum(delta, axis=0, keepdims=True)
        self.v_b[layer] = beta2 * self.v_b[layer] + (1 - beta2) * np.square(np.sum(delta, axis=0, keepdims=True))
        m_hat_b = self.m_b[layer] / (1 - beta1**t)
        v_hat_b = self.v_b[layer] / (1 - beta2**t)
        self.biases[layer] += learning_rate * m_hat_b / (np.sqrt(v_hat_b) + epsilon)

# -------------------------
# Tipos de activación para el componente cuántico-clásico (redefinidos)
# -------------------------
class ActivationType(Enum):
    SIGMOID = "sigmoid"
    TANH = "tanh"
    RELU = "relu"

# -------------------------
# Componente Híbrido: Activador Cuántico-Clásico (redefinido)
# -------------------------
class QuantumClassicalActivator:
    def __init__(self, n_qubits: int = 3):
        """
        Inicializa el sistema híbrido cuántico-clásico.

        Args:
            n_qubits (int): Número de qubits para el registro cuántico.
        """
        self.n_qubits = n_qubits
        self._setup_activation_functions()

    def _setup_activation_functions(self):
        """Configura funciones de activación y sus derivadas."""
        self.activation_functions = {
            ActivationType.SIGMOID: sigmoid,
            ActivationType.TANH: tanh,
            ActivationType.RELU: relu
        }
        self.activation_derivatives = {
            ActivationType.SIGMOID: sigmoid_derivative,
            ActivationType.TANH: tanh_derivative,
            ActivationType.RELU: relu_derivative
        }

    def create_quantum_circuit(self, activation_type: ActivationType) -> QuantumCircuit:
        """
        Crea un circuito cuántico que simula una versión controlada de la función de activación.

        Args:
            activation_type (ActivationType): Tipo de función de activación a implementar.

        Returns:
            QuantumCircuit: Circuito cuántico generado.
        """
        qr = QuantumRegister(self.n_qubits, 'q')
        cr = ClassicalRegister(self.n_qubits, 'c')
        qc = QuantumCircuit(qr, cr)
        theta = Parameter('θ')
        if activation_type == ActivationType.SIGMOID:
            qc.h(qr[0])
            qc.cry(theta, qr[0], qr[1])
            qc.cx(qr[1], qr[2])
        elif activation_type == ActivationType.TANH:
            qc.h(qr[0])
            qc.cp(theta, qr[0], qr[1])
            qc.rz(theta/2, qr[1])
        elif activation_type == ActivationType.RELU:
            qc.x(qr[0])
            qc.ch(qr[0], qr[1])
            qc.measure_all()
        return qc

    def quantum_activated_forward(self,
                                  x: np.ndarray,
                                  activation_type: ActivationType,
                                  collapse_threshold: float = 0.5) -> Tuple[np.ndarray, float]:
        """
        Realiza una propagación forward híbrida combinando activación clásica con
        colapso cuántico controlado.

        Args:
            x (np.ndarray): Datos de entrada.
            activation_type (ActivationType): Tipo de activación.
            collapse_threshold (float): Umbral para determinar colapso.

        Returns:
            Tuple[np.ndarray, float]: Salida activada y probabilidad de colapso.
        """
        classic_out = self.activation_functions[activation_type](x)
        collapse_prob = np.mean(np.abs(classic_out))  # Umbral basado en la magnitud promedio
        if collapse_prob > collapse_threshold:
            quantum_factor = np.sqrt(1 - collapse_prob)
            modified_out = classic_out * quantum_factor
        else:
            modified_out = classic_out
        return modified_out, collapse_prob

    def hybrid_backpropagation(self,
                               gradient: np.ndarray,
                               activation_type: ActivationType,
                               collapse_probability: float) -> np.ndarray:
        """
        Retropropagación híbrida considerando la función de activación y el efecto de colapso.

        Args:
            gradient (np.ndarray): Gradiente de la capa siguiente.
            activation_type (ActivationType): Tipo de activación.
            collapse_probability (float): Probabilidad de colapso.

        Returns:
            np.ndarray: Gradiente modificado.
        """
        classical_deriv = self.activation_derivatives[activation_type]
        quantum_factor = np.sqrt(1 - collapse_probability)
        modified_grad = gradient * classical_deriv(gradient) * quantum_factor
        return modified_grad

# -------------------------
# Clase QuantumState (combinando la versión más completa de init_activation)
# -------------------------
class QuantumState(QuantumBayesMahalanobis):
    """
    Gestiona el estado cuántico utilizando métodos bayesianos, distancias de Mahalanobis,
    y expandiendo con una representación en forma de vector de probabilidades.

    Provee métodos para predecir y actualizar el estado.
    """
    def __init__(self, num_positions: int, learning_rate: float = 0.1):
        super().__init__()  # Inicializa la parte avanzada cuántica
        self.num_positions = num_positions
        self.learning_rate = learning_rate
        self.state_vector = np.random.rand(num_positions)
        self.state_vector = self.normalize_state(self.state_vector)
        self.probabilities = self.state_vector.copy()

    @staticmethod
    def normalize_state(state: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(state)
        return state / norm if norm != 0 else state

    def predict_state_update(self) -> Tuple[np.ndarray, float]:
        """
        Usa el método predict_quantum_state (por herencia) para calcular la predicción del siguiente estado.
        Se calculan valores de entropía y coherencia (utilizando StatisticalAnalysis) para alimentar la predicción.

        Returns:
            Tuple[np.ndarray, float]: (Nuevo estado predicho, posterior)
        """
        current_input = np.array([self.state_vector])
        entropy = StatisticalAnalysis.shannon_entropy(self.state_vector)
        coherence = np.mean(self.state_vector)
        next_state_tensor, posterior = self.predict_quantum_state(current_input, entropy, coherence)
        next_state = next_state_tensor.numpy().flatten()
        next_state = self.normalize_state(next_state)
        return next_state, posterior

    def update_state(self, action: int) -> None:
        """
        Actualiza el estado cuántico combinando el estado actual con el estado predicho,
        ponderado por la tasa de aprendizaje e influenciado por la acción.

        Args:
            action (int): Acción tomada (0 o 1) que influirá en la actualización del estado.
        """
        # Predecir el siguiente estado
        next_state, posterior = self.predict_state_update()

        # Modificar la actualización basada en la acción
        if action == 1:
            # Acción positiva: explorar más el nuevo estado
            update_factor = self.learning_rate * (1 + posterior)
        else:
            # Acción negativa: mantener más el estado actual
            update_factor = self.learning_rate * (1 - posterior)

        # Actualizar estado con factor de aprendizaje dinámico
        updated_state = (1 - update_factor) * self.state_vector + update_factor * next_state

        # Normalizar y actualizar
        self.state_vector = self.normalize_state(updated_state)

        # Actualizar probabilidades
        self.probabilities = np.abs(self.state_vector)

    def compute_quantum_uncertainty(self) -> float:
        """
        Calcula la incertidumbre del estado cuántico basada en la entropía de Shannon.

        Returns:
            float: Valor de incertidumbre (0-1)
        """
        entropy = StatisticalAnalysis.shannon_entropy(np.abs(self.probabilities))
        return entropy

    def quantum_interference(self, other_state: 'QuantumState') -> np.ndarray:
        """
        Simula la interferencia cuántica entre dos estados.

        Args:
            other_state (QuantumState): Otro estado cuántico para interferir.

        Returns:
            np.ndarray: Estado resultante de la interferencia.
        """
        # Producto punto complejo
        interference_pattern = np.dot(
            np.abs(self.state_vector),
            np.abs(other_state.state_vector)
        )

        # Generar nuevo estado con patrón de interferencia
        new_state = self.state_vector * np.cos(interference_pattern)

        return self.normalize_state(new_state)

    def quantum_entanglement_measure(self, other_state: 'QuantumState') -> float:
        """
        Calcula una medida de entrelazamiento entre dos estados cuánticos.

        Args:
            other_state (QuantumState): Otro estado cuántico para medir entrelazamiento.

        Returns:
            float: Medida de entrelazamiento (0-1)
        """
        # Producto tensorial de probabilidades
        tensor_product = np.outer(
            np.abs(self.probabilities),
            np.abs(other_state.probabilities)
        )

        # Calcular entrelazamiento basado en la entropía del producto tensorial
        entanglement_entropy = StatisticalAnalysis.shannon_entropy(tensor_product.flatten())

        return entanglement_entropy

    def visualize_state(self) -> dict:
        """
        Proporciona una visualización detallada del estado cuántico.

        Returns:
            dict: Diccionario con información del estado.
        """
        return {
            'state_vector': self.state_vector.tolist(),
            'probabilities': self.probabilities.tolist(),
            'uncertainty': self.compute_quantum_uncertainty(),
            'norm': np.linalg.norm(self.state_vector)
        }

    def quantum_measurement(self, observable: np.ndarray = None) -> float:
        """
        Realiza una medición del estado cuántico con un observable opcional.

        Args:
            observable (np.ndarray, opcional): Matriz de observable. Si no se proporciona,
                                               se usa el vector de estado actual.

        Returns:
            float: Valor de expectación de la medición.
        """
        if observable is None:
            observable = np.diag(self.probabilities)

        # Calcular valor de expectación
        expectation_value = np.dot(
            self.state_vector.T,
            np.dot(observable, self.state_vector)
        )

        return np.real(expectation_value)

    # Método para serializar el estado cuántico
    def serialize_state(self) -> dict:
        """
        Serializa el estado cuántico para persistencia.

        Returns:
            dict: Diccionario con información serializable del estado.
        """
        return {
            'state_vector': self.state_vector.tolist(),
            'probabilities': self.probabilities.tolist(),
            'num_positions': self.num_positions,
            'learning_rate': self.learning_rate
        }

    @classmethod
    def deserialize_state(cls, serialized_data: dict) -> 'QuantumState':
        """
        Deserializa un estado cuántico previamente serializado.

        Args:
            serialized_data (dict): Datos serializados del estado.

        Returns:
            QuantumState: Estado cuántico reconstruido.
        """
        quantum_state = cls(
            num_positions=serialized_data['num_positions'],
            learning_rate=serialized_data['learning_rate']
        )
        quantum_state.state_vector = np.array(serialized_data['state_vector'])
        quantum_state.probabilities = np.array(serialized_data['probabilities'])

        return quantum_state

# -------------------------
# Ejemplo de uso combinado
# -------------------------
if __name__ == "__main__":
    # Ejemplo de la red neuronal clásica
    nn = NeuralNetwork(input_size=3, hidden_size=[4, 3], output_size=2, activation="sigmoid")
    x_sample = np.array([[0.5, -0.2, 0.8]])
    activations = nn.forward(x_sample)
    print("Activaciones de la red neural:")
    for a in activations:
        print(a)

    # Ejemplo del activador híbrido cuántico-clásico
    hybrid_activator = QuantumClassicalActivator(n_qubits=3)
    activated_output, collapse_prob = hybrid_activator.quantum_activated_forward(x_sample.flatten(), ActivationType.SIGMOID, collapse_threshold=0.6)
    print("\nSalida activada híbrida:")
    print(activated_output)
    print("Probabilidad de colapso:", collapse_prob)

    quantum_circuit = hybrid_activator.create_quantum_circuit(ActivationType.SIGMOID)
    print("\nCircuito cuántico generado:")
    print(quantum_circuit)

    # Ejemplo del estado cuántico (con las funcionalidades extendidas)
    qs1 = QuantumState(num_positions=5, learning_rate=0.1)
    qs2 = QuantumState(num_positions=5, learning_rate=0.1)
    print("\nEstado cuántico inicial 1:", qs1.visualize_state())
    print("Estado cuántico inicial 2:", qs2.visualize_state())

    qs1.update_state(action=1)
    qs2.update_state(action=0)
    print("\nEstado cuántico 1 tras actualización:", qs1.visualize_state())
    print("Estado cuántico 2 tras actualización:", qs2.visualize_state())

    uncertainty1 = qs1.compute_quantum_uncertainty()
    print("\nIncertidumbre del estado cuántico 1:", uncertainty1)

    interference_state = qs1.quantum_interference(qs2)
    print("\nEstado tras interferencia:", QuantumState.normalize_state(interference_state))

    entanglement = qs1.quantum_entanglement_measure(qs2)
    print("\nMedida de entrelazamiento entre qs1 y qs2:", entanglement)

    serialized_state = qs1.serialize_state()
    print("\nEstado cuántico 1 serializado:", serialized_state)
    deserialized_state = QuantumState.deserialize_state(serialized_state)
    print("\nEstado cuántico 1 deserializado:", deserialized_state.visualize_state())

